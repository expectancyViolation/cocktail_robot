import logging
import uuid
from collections import deque
from dataclasses import dataclass
from enum import Enum
from itertools import groupby
from typing import Iterable, Generator

from cocktail_24.cocktail_robo import (
    CocktailRobotPumpTask,
    CocktailPosition,
    CocktailRobotTask,
)
from cocktail_24.cocktail_robot_interface import (
    CocktailRobot,
    CocktailRobotTaskExecution,
    CocktailRoboState,
)
from cocktail_24.pump_interface.pump_interface import PumpInterface, PumpStatus


@dataclass(frozen=True)
class GetTimeEffect: ...


@dataclass(frozen=True)
class GetTimeResponse:
    time: float


@dataclass(frozen=True)
class PumpSendEffect:
    to_send: bytes


@dataclass(frozen=True)
class PumpSendResponse:
    pass


@dataclass(frozen=True)
class CocktailRobotSendEffect:
    to_send: str


@dataclass(frozen=True)
class CocktailRobotSendResponse:
    resp: str


CocktailSystemEffect = CocktailRobotSendEffect | GetTimeEffect | PumpSendEffect


class CocktailSystemStatus(Enum):
    initializing_plan = "initializing_plan"
    feeding_robot = "feeding_robot"
    pumping = "pumping"
    idle = "idle"


@dataclass(frozen=True)
class CocktailSystemPlan:
    plan_uuid: uuid.uuid4()
    steps: tuple[CocktailRobotTask, ...]

    def prettyprint(self) -> str:
        res = f"Plan {self.plan_uuid}\n"
        step_strings = []
        for i, step in enumerate(self.steps):
            step_strings.append(f"step {i:03n}:{step}")
        return res + "\n".join(step_strings)


@dataclass(frozen=True)
class PlanProgress:
    plan: CocktailSystemPlan
    queued_step_pos: int
    finished_step_pos: int

    def is_finished(self):
        return self.finished_step_pos + 1 == len(self.plan.steps)

    def update(
        self, queued_step_pos: int | None = None, finished_step_pos: int | None = None
    ) -> "PlanProgress":
        new_queued_step_pos = (
            queued_step_pos if queued_step_pos is not None else self.queued_step_pos
        )
        new_finished_step_pos = (
            finished_step_pos
            if finished_step_pos is not None
            else self.finished_step_pos
        )
        return PlanProgress(
            plan=self.plan,
            queued_step_pos=new_queued_step_pos,
            finished_step_pos=new_finished_step_pos,
        )


@dataclass(frozen=True)
class CocktailSystemState:
    status: CocktailSystemStatus
    plan_progress: PlanProgress
    robot_state: CocktailRoboState
    pump_status: PumpStatus


def _wrap_tcp_effect_[
    T
](gen: Generator[str | None, str | None, T]) -> Generator[
    CocktailRobotSendEffect, CocktailRobotSendResponse, T
]:
    x: str = next(gen)
    try:
        while True:
            resp = yield CocktailRobotSendEffect(to_send=x)
            assert isinstance(resp, CocktailRobotSendResponse)
            x = gen.send(resp.resp)
    except StopIteration as e:
        return e.value


class CocktailSystem:

    def __init__(
        self, robot: CocktailRobot, pump: PumpInterface, initial_time: float = 0
    ):
        self._robot_ = robot
        self._robot_operation_ = robot.gen_operate()
        self._pump_ = pump
        self._state_ = CocktailSystemStatus.idle
        self._robot_effect_ = CocktailRobotSendEffect(
            to_send=next(self._robot_operation_)
        )
        self._current_time_ = initial_time
        self._events_ = []
        self._plan_progress_: PlanProgress | None = None
        self._plan_execution_: Generator[None, None, None] | None = None
        self._stopped_ = False

    # def get_progress(self) -> PlanProgress | None:
    #     return self._plan_progress_

    def gen_initialize(self, connect: bool = True):
        yield from _wrap_tcp_effect_(self._robot_.gen_initialize(connect=connect))
        yield from _wrap_tcp_effect_(self._robot_.gen_initialize_job())

    def run_plan(self, plan: CocktailSystemPlan):
        assert self._state_ == CocktailSystemStatus.idle
        assert self._plan_execution_ is None
        self._state_ = CocktailSystemStatus.initializing_plan
        self._plan_progress_ = PlanProgress(
            plan=plan, queued_step_pos=-1, finished_step_pos=-1
        )
        self._plan_execution_ = self.gen_execute_plan(plan)
        return self._plan_progress_

    def get_state(self):
        # TODO: DANGER states of system,robot and pump are not "temporary consistent"
        #   i.e. cocktail system might not have processed partial robot state update
        #   use system state for decisions!
        return CocktailSystemState(
            status=self._state_,
            plan_progress=self._plan_progress_,
            robot_state=self._robot_.robo_state,
            pump_status=self._pump_.status,
        )

    def gen_run(self):
        while not self._stopped_:
            yield from self.gen_handle_effects()
            if self._state_ == CocktailSystemStatus.idle:
                pass
            else:
                assert self._plan_execution_ is not None
                try:
                    next(self._plan_execution_)
                except StopIteration as e:
                    print(f"execution result {e}")
                    self._state_ = CocktailSystemStatus.idle
                    self._plan_execution_ = None

    # handle effects (this is "fair share" atm, so everyone gets one step each)
    def gen_handle_effects(self):
        current_time_resp = yield GetTimeEffect()
        assert isinstance(current_time_resp, GetTimeResponse)
        self._current_time_ = current_time_resp.time
        robot_is_at_pump = self._robot_.robo_state.position == CocktailPosition.pump
        self._pump_.update(self._current_time_, robot_is_at_pump)
        pump_msg = self._pump_.get_pump_msg()
        _pump_resp = yield PumpSendEffect(pump_msg)

        # handle robot
        resp = yield self._robot_effect_
        assert isinstance(resp, CocktailRobotSendResponse)
        try:
            self._robot_effect_ = CocktailRobotSendEffect(
                self._robot_operation_.send(resp.resp)
            )
        except StopIteration as e:
            logging.warning("detected robot stop. stopping system")
            self._stopped_ = True

    def check_finished_robo_tasks(self):
        # robot
        finished_task_ids = self._robot_.pop_finished_tasks()
        if finished_task_ids:
            print(f"got finished tasks: {finished_task_ids}")
            for id_ in finished_task_ids:
                # task is next task
                assert self._plan_progress_.finished_step_pos + 1 == id_
                self._plan_progress_ = self._plan_progress_.update(
                    finished_step_pos=id_
                )

    # feed robot queue (this avoids unnecessary pauses due to the slow network interface)
    def gen_handle_robot_steps(
        self, numbered_robot_steps: Iterable[tuple[int, CocktailRobotTask]]
    ):
        task_execs = deque(
            [
                CocktailRobotTaskExecution(task_id=step_num, task=step)
                for step_num, step in numbered_robot_steps
            ]
        )
        last_step_num = task_execs[-1].task_id
        while self._plan_progress_.finished_step_pos < last_step_num:
            yield
            self.check_finished_robo_tasks()
            if len(task_execs) > 0:
                could_enqueue = self._robot_.enqueue_task(task_execs[0])
                if could_enqueue:
                    self._plan_progress_ = self._plan_progress_.update(
                        queued_step_pos=task_execs[0].task_id
                    )
                    task_execs.popleft()

    # sequentially handle pumps
    def gen_handle_pump_steps(
        self, numbered_pump_steps: Iterable[tuple[int, CocktailRobotPumpTask]]
    ):
        for step_num, pump_step in numbered_pump_steps:
            assert self._pump_.status == PumpStatus.ready
            self._pump_.request_pump(pump_step)
            self._plan_progress_ = self._plan_progress_.update(queued_step_pos=step_num)
            while self._pump_.status == PumpStatus.pumping:
                yield
            self._pump_.reset()
            self._plan_progress_ = self._plan_progress_.update(
                finished_step_pos=step_num
            )

    def gen_execute_plan(self, plan: CocktailSystemPlan):
        step_groups = groupby(
            enumerate(plan.steps),
            key=lambda tup: isinstance(tup[1], CocktailRobotPumpTask),
        )
        for is_pump, numbered_steps in step_groups:
            if not is_pump:
                self._state_ = CocktailSystemStatus.feeding_robot
                yield from self.gen_handle_robot_steps(numbered_steps)
            else:
                self._state_ = CocktailSystemStatus.pumping
                yield from self.gen_handle_pump_steps(numbered_steps)
        # handle effects once more for good measure
        self._state_ = CocktailSystemStatus.idle
