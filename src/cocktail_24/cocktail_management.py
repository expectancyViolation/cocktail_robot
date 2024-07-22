import datetime
import logging
from typing import Protocol

from cocktail_24.cocktail.cocktail_api import (
    CocktailBarStatePersistence,
    EventOccurrence,
)
from cocktail_24.cocktail.cocktail_bookkeeping import (
    CocktailBarEvent,
    OrderStatus,
    Order,
    OrderFulfilledEvent,
    OrderExecutingEvent,
    OrderAbortedEvent,
)
from cocktail_24.cocktail.cocktail_recipes import CocktailRecipe
from cocktail_24.cocktail_system import (
    CocktailSystem,
    CocktailSystemState,
    PlanProgress,
    CocktailSystemStatus,
    CocktailSystemPlan,
)
from cocktail_24.planning.cocktail_planner import CocktailSystemConfig
from cocktail_24.planning.cocktail_planning import StaticCocktailPlanning


class CocktailManagementCocktailSystem(Protocol):

    def get_state(self) -> CocktailSystemState: ...

    def run_plan(self) -> PlanProgress: ...


class FakeFulfillmentSystem(CocktailManagementCocktailSystem):

    def get_state(self) -> CocktailSystemState: ...


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
        self._old_system_state_ = cocktail_system.get_state()
        self._old_progress_: None | PlanProgress = None
        self._system_config_ = system_config
        self._active_order_: None | Order = None

    def get_system(self):
        return self._system_

    def check_progress(self, new_plan_progress: PlanProgress):
        # TODO: this is kinda bad: system should produce events?
        if new_plan_progress != self._old_progress_:
            if (new_plan_progress is not None) and (self._old_progress_ is not None):
                print(
                    f"calc progress {new_plan_progress.finished_step_pos} from {self._old_progress_.finished_step_pos}"
                )
                plan_progression_events = self._planning_.get_consequences(
                    system_config=self._system_config_,
                    prior_plan_progress=self._old_system_state_.plan_progress,
                    current_plan_progress=new_plan_progress,
                )

                plan_is_done = new_plan_progress.is_finished()
                if plan_is_done:
                    plan_progression_events += (
                        OrderFulfilledEvent(self._active_order_.order_id),
                    )

                # DANGER dependency time
                timed_events = [
                    EventOccurrence(event=ev, timestamp=datetime.datetime.now())
                    for ev in plan_progression_events
                ]
                self._persistence_.persist_events(timed_events)
                self._old_progress_ = new_plan_progress
            else:
                logging.warning(
                    f"None progress {new_plan_progress} {self._old_progress_}"
                )

    def abort(self):
        if self._active_order_ is not None:
            timed_events = [
                EventOccurrence(
                    event=OrderAbortedEvent(self._active_order_.order_id),
                    timestamp=datetime.datetime.now(),
                )
            ]
            self._persistence_.persist_events(timed_events)

    def check_update(self):
        new_system_state = self._system_.get_state()
        new_plan_progress = new_system_state.plan_progress
        self.check_progress(new_plan_progress)

        if new_system_state != self._old_system_state_:
            if new_system_state.robot_state != self._old_system_state_.robot_state:
                logging.warning(
                    f"Robo state change: {self._old_system_state_.robot_state}->{new_system_state.robot_state}"
                )
            if new_system_state.status != self._old_system_state_.status:
                logging.warning(
                    f"System status change: {self._old_system_state_.status}->{new_system_state.status}"
                )
            if new_system_state.pump_status != self._old_system_state_.pump_status:
                logging.warning(
                    f"Pump status change: {self._old_system_state_.pump_status}->{new_system_state.pump_status}"
                )

        bar_state = self._persistence_.get_current_state()
        # print(f"checking bar state {bar_state}")
        if new_system_state.status == CocktailSystemStatus.idle:
            order_queue = bar_state.order_queue
            if order_queue:
                print("pulling from order queue")
                next_order_id = order_queue[0]
                next_order = bar_state.orders[next_order_id]
                print(f"next order is {next_order}")

                assert next_order.status == OrderStatus.enqueued

                timed_events = [
                    EventOccurrence(
                        event=OrderExecutingEvent(next_order_id),
                        timestamp=datetime.datetime.now(),
                    )
                ]
                self._persistence_.persist_events(timed_events)

                recipe = bar_state.recipes[next_order.recipe_id]
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

        self._old_system_state_ = new_system_state
