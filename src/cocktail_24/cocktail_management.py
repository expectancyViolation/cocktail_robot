import datetime
import logging
from typing import Protocol, Iterable

from cocktail_24.cocktail.cocktail_api import (
    CocktailBarStatePersistence,
    EventOccurrence,
)
from cocktail_24.cocktail.cocktail_bookkeeping import (
    OrderStatus,
    Order,
    OrderFulfilledEvent,
    OrderExecutingEvent,
    OrderAbortedEvent,
    CocktailBarEvent,
)
from cocktail_24.cocktail_robo import CocktailPosition
from cocktail_24.cocktail_robot_interface import CocktailRobotState
from cocktail_24.cocktail_system import (
    CocktailSystemState,
    PlanProgress,
    CocktailSystemStatus,
    CocktailSystemPlan,
)
from cocktail_24.planning.cocktail_planner import (
    CocktailSystemConfig,
    IngredientsMissingException,
)
from cocktail_24.planning.cocktail_planning import StaticCocktailPlanning
from cocktail_24.pump_interface.pump_interface import PumpStatus


class CocktailManagementCocktailSystem(Protocol):

    def get_state(self) -> CocktailSystemState: ...

    def run_plan(self, plan: CocktailSystemPlan) -> PlanProgress: ...


class FakeFulfillmentSystem(CocktailManagementCocktailSystem):

    def __init__(self):
        self.progress: PlanProgress | None = None

    def run_plan(self, plan: CocktailSystemPlan) -> PlanProgress:
        self.progress = PlanProgress(plan, queued_step_pos=-1, finished_step_pos=-1)

    def _step_progress_(self):
        if self.progress is None:
            return
        if not self.progress.is_finished():
            self.progress = self.progress.update(
                finished_step_pos=1 + self.progress.finished_step_pos
            )

    def get_state(self) -> CocktailSystemState:
        self._step_progress_()
        return CocktailSystemState(
            status=(
                CocktailSystemStatus.idle
                if (self.progress is None) or (self.progress.is_finished())
                else CocktailSystemStatus.feeding_robot
            ),
            robot_state=CocktailRobotState(
                position=CocktailPosition.home,
                shaker_empty=True,
                cup_full=True,
                cup_placed=True,
                cup_id=233,
                ringbuffer_read_pos=0,
            ),
            pump_status=PumpStatus.ready,
            plan_progress=self.progress,
        )


class CocktailManagement:

    def __init__(
        self,
        cocktail_persistence: CocktailBarStatePersistence,
        cocktail_system: CocktailManagementCocktailSystem,
        planning: StaticCocktailPlanning,
        system_config: CocktailSystemConfig,
    ):
        self._persistence_ = cocktail_persistence
        self._system_ = cocktail_system
        self._planning_ = planning
        # self._old_system_state_ = cocktail_system.get_state()
        self._old_progress_: None | PlanProgress = None
        self._system_config_ = system_config
        self._active_order_: None | Order = None

    def get_system(self):
        return self._system_

    def check_progress(self, new_plan_progress: PlanProgress):
        # TODO: this is kinda bad: system should produce events?
        if new_plan_progress != self._old_progress_:
            if new_plan_progress is not None:
                if self._old_progress_ is None:
                    logging.warning("None old progress: assuming zero")
                    self._old_progress_ = PlanProgress(
                        new_plan_progress.plan, queued_step_pos=-1, finished_step_pos=-1
                    )
                print(
                    f"calc progress {new_plan_progress.finished_step_pos} from {self._old_progress_.finished_step_pos}"
                )
                plan_progression_events = self._planning_.get_consequences(
                    system_config=self._system_config_,
                    prior_plan_progress=self._old_progress_,
                    current_plan_progress=new_plan_progress,
                )

                plan_is_done = new_plan_progress.is_finished()
                if plan_is_done:
                    plan_progression_events += (
                        OrderFulfilledEvent(self._active_order_.order_id),
                    )

                self._persist_(plan_progression_events)
                self._old_progress_ = new_plan_progress
            else:
                pass
                # logging.warning(
                #     f"None progress {new_plan_progress} {self._old_progress_}"
                # )

    # DANGER dependency: time
    def _persist_(self, events: Iterable[CocktailBarEvent]):
        timed_events = [
            EventOccurrence(
                event=event,
                timestamp=datetime.datetime.now(),
            )
            for event in events
        ]
        self._persistence_.persist_events(timed_events)

    def abort(self):
        if self._active_order_ is not None:
            self._persist_([OrderAbortedEvent(self._active_order_.order_id)])

    def check_update(self):
        # TODO: this read might contain stale data (if persistence is async)
        bar_state = self._persistence_.get_current_state()
        new_system_state = self._system_.get_state()
        new_plan_progress = new_system_state.plan_progress
        # DANGER: this generates events, that are not reflected in bar_state for the rest of the update!
        self.check_progress(new_plan_progress)

        if new_system_state.status == CocktailSystemStatus.idle:
            order_queue = bar_state.order_queue
            if order_queue:
                next_order_id = order_queue[0]
                next_order = bar_state.orders[next_order_id]
                logging.info(f"pulled from order queue {next_order}")

                assert next_order.status == OrderStatus.enqueued
                self._persist_([OrderExecutingEvent(next_order_id)])

                recipe = bar_state.recipes[next_order.recipe_id]
                try:
                    plan = self._planning_.plan_cocktail(
                        recipe,
                        slots_status=bar_state.slots,
                        robot_position=new_system_state.robot_state.position,
                        shaker_empty=new_system_state.robot_state.shaker_empty,
                    )
                    logging.warning("sending new plan:")
                    logging.warning("--------")
                    logging.warning(plan.prettyprint())
                    self._old_progress_ = self._system_.run_plan(plan)
                    self._active_order_ = next_order
                except IngredientsMissingException as e:
                    logging.warning(f"order cannot be handled {e}")

        # self._old_system_state_ = new_system_state
