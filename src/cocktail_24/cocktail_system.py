import uuid
from collections import deque
from dataclasses import dataclass
from enum import Enum
from itertools import groupby
from typing import Iterable, Generator

from cocktail_24.cocktail.cocktail_recipes import CocktailRecipe
from cocktail_24.cocktail_robo import (
    RecipeCocktailPlannerFactory,
    CocktailRobotPumpTask,
    CocktailPosition,
    CocktailRobotTask,
)
from cocktail_24.cocktail_robot_interface import (
    CocktailRobot,
    CocktailRobotTaskExecution,
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


class CocktailSystemState(Enum):
    initializing = "initializing"
    feeding_robot = "feeding_robot"
    pumping = "pumping"
    idle = "idle"


@dataclass(frozen=True)
class CocktailSystemPlan:
    plan_uuid: uuid.uuid4()
    steps: tuple[CocktailRobotTask]


@dataclass
class PlanProgress:
    plan: CocktailSystemPlan
    queued_step_pos: int
    finished_step_pos: int

    def is_finished(self):
        return self.finished_step_pos + 1 == len(self.plan.steps)


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
        self._state_ = CocktailSystemState.feeding_robot
        self._robot_effect_ = CocktailRobotSendEffect(
            to_send=next(self._robot_operation_)
        )
        self._current_time_ = initial_time
        self._events_ = []
        self._plan_progress_: PlanProgress | None = None


    def gen_initialize(self):
        yield from _wrap_tcp_effect_(self._robot_.gen_initialize())
        yield from _wrap_tcp_effect_(self._robot_.gen_initialize_job())

    def gen_idle_behaviour(self):
        yield from self.gen_handle_effects()

    # handle effects (this is "fair share" atm, so everyone gets one step each)
    def gen_handle_effects(self):
        current_time_resp = yield GetTimeEffect()
        assert isinstance(current_time_resp, GetTimeResponse)
        self._current_time_ = current_time_resp.time
        robot_is_at_pump = self._robot_.robo_state.position == CocktailPosition.pump
        self._pump_.update(self._current_time_, robot_is_at_pump)
        pump_msg = self._pump_.get_pump_msg()
        _pump_resp = yield PumpSendEffect(pump_msg)
        resp = yield self._robot_effect_
        assert isinstance(resp, CocktailRobotSendResponse)
        self._robot_effect_ = CocktailRobotSendEffect(
            self._robot_operation_.send(resp.resp)
        )

    def check_finished_robo_tasks(self):
        # robot
        finished_task_ids = self._robot_.pop_finished_tasks()
        if finished_task_ids:
            print(f"got finished tasks: {finished_task_ids}")
            for id_ in finished_task_ids:
                # task is next task
                assert self._plan_progress_.finished_step_pos + 1 == id_
                self._plan_progress_.finished_step_pos = id_

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
            yield from self.gen_handle_effects()
            self.check_finished_robo_tasks()
            if len(task_execs) > 0:
                could_enqueue = self._robot_.enqueue_task(task_execs[0])
                if could_enqueue:
                    self._plan_progress_.queued_step_pos = task_execs[0].task_id
                    task_execs.popleft()

    # sequentially handle pumps
    def gen_handle_pump_steps(
        self, numbered_pump_steps: Iterable[tuple[int, CocktailRobotPumpTask]]
    ):
        for step_num, pump_step in numbered_pump_steps:
            assert self._pump_.status == PumpStatus.ready
            self._pump_.request_pump(pump_step)
            self._plan_progress_.queued_step_pos = step_num
            while self._pump_.status == PumpStatus.pumping:
                yield from self.gen_handle_effects()
            self._pump_.reset()
            self._plan_progress_.finished_step_pos = step_num

    def gen_execute_plan(self, plan: CocktailSystemPlan):
        self._plan_progress_ = PlanProgress(
            plan=plan, queued_step_pos=-1, finished_step_pos=-1
        )
        step_groups = groupby(
            enumerate(plan.steps),
            key=lambda tup: isinstance(tup[1], CocktailRobotPumpTask),
        )
        for is_pump, numbered_steps in step_groups:
            if not is_pump:
                self._state_ = CocktailSystemState.feeding_robot
                yield from self.gen_handle_robot_steps(numbered_steps)
            else:
                self._state_ = CocktailSystemState.pumping
                yield from self.gen_handle_pump_steps(numbered_steps)
        # handle effects once more for good measure
        yield from self.gen_handle_effects()
        self._state_ = CocktailSystemState.idle
