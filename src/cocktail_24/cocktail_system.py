import uuid
from collections import deque
from dataclasses import dataclass
from enum import Enum

from cocktail_24.cocktail_recipes import CocktailRecipe
from cocktail_24.cocktail_robo import RecipeCocktailPlannerFactory, CocktailRobotPumpTask, \
    CocktailPosition
from cocktail_24.cocktail_robot_interface import CocktailRobot, CocktailRobotSendEffect, CocktailRobotPullWorkEffect, \
    CocktailRobotPullWorkResponse, CocktailRobotReportWorkDoneEffect
from cocktail_24.pump_interface.pump_interface import PumpInterface, PumpStatus


@dataclass(frozen=True)
class GetTimeEffect:
    ...


@dataclass(frozen=True)
class GetTimeResponse:
    time: float


@dataclass(frozen=True)
class PumpSendEffect:
    to_send: bytes


@dataclass(frozen=True)
class PumpSendResponse:
    pass


CocktailSystemEffect = CocktailRobotSendEffect | GetTimeEffect | PumpSendEffect


class CocktailSystemState(Enum):
    initializing = "initializing"
    feeding_robot = "feeding_robot"
    pumping = "pumping"


class CocktailSystem:

    def __init__(self, robot: CocktailRobot, pump: PumpInterface, planner_factory: RecipeCocktailPlannerFactory):
        self._robot_ = robot
        self._planner_factory_ = planner_factory
        self._pump_ = pump
        self._state_ = CocktailSystemState.initializing
        # self._robot_task_queue_ = []

    # recipes must be fed
    def gen_handle_cocktail_recipe(self, recipe: CocktailRecipe):
        planner = self._planner_factory_.get_planner(recipe)
        gen_plan = planner.gen_plan_pour_cocktail()
        gen_handle = self._robot_.gen_pour_cocktail()
        effect = next(gen_handle)

        DONE = "DONE"

        def determine_next_task():
            try:
                res = next(gen_plan)
            except StopIteration:
                res = DONE
            print(f"determined next task {res}")
            return res

        robo_task_queue = deque()

        next_task = determine_next_task()

        def is_done():
            return len(robo_task_queue) == 0 and (next_task == "DONE")

        while not is_done():
            current_time_resp = yield GetTimeEffect()
            assert isinstance(current_time_resp, GetTimeResponse)
            current_time = current_time_resp.time

            robot_is_idle = len(robo_task_queue) == 0
            next_is_pump = isinstance(next_task, CocktailRobotPumpTask)

            pump_now = robot_is_idle and next_is_pump

            if pump_now:
                self._pump_.request_pump(next_task)
                next_task = None
                self._state_ = CocktailSystemState.pumping

            robo_state = self._robot_.robo_state

            robot_is_at_pump = robo_state.position == CocktailPosition.pump

            # handle pump needs
            self._pump_.update(current_time, robot_is_at_pump)
            if self._state_ == CocktailSystemState.pumping:
                print(self._pump_.pump_durations)
                match self._pump_.status:
                    case PumpStatus.pumping:
                        pass
                    case _:
                        print(f"pump stopped {self._pump_.status}")
                        self._pump_.reset()
                        next_task = determine_next_task()
                        self._state_ = CocktailSystemState.feeding_robot

            pump_msg = self._pump_.get_pump_msg()
            resp = yield PumpSendEffect(pump_msg)
            assert isinstance(resp, PumpSendResponse)

            # handle robot needs
            match effect:
                case CocktailRobotSendEffect():
                    resp = yield effect
                    effect = gen_handle.send(resp)
                case CocktailRobotPullWorkEffect():
                    if next_is_pump or (next_task is None) or (next_task is DONE):
                        effect = gen_handle.send(None)
                    else:
                        task_id = uuid.uuid4()
                        effect = gen_handle.send(CocktailRobotPullWorkResponse(task=next_task, task_id=task_id))
                        robo_task_queue.append((task_id, next_task))
                        next_task = determine_next_task()
                case CocktailRobotReportWorkDoneEffect(task_id):
                    print(robo_task_queue)
                    oldest_task_id, oldest_task = robo_task_queue.popleft()
                    print(oldest_task_id, task_id, oldest_task)
                    assert oldest_task_id == task_id
                    print(f"finished {oldest_task}")
                    effect = next(gen_handle)
                case _:
                    raise Exception(f"unknown effect {effect}")
