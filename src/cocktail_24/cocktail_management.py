from typing import Protocol

from cocktail_24.cocktail.cocktail_api import CocktailBarStatePersistence
from cocktail_24.cocktail.cocktail_bookkeeping import CocktailBarEvent, OrderStatus
from cocktail_24.cocktail.cocktail_recipes import CocktailRecipe
from cocktail_24.cocktail_system import (
    CocktailSystem,
    CocktailSystemState,
    PlanProgress,
    CocktailSystemStatus,
    CocktailSystemPlan,
)
from cocktail_24.planning.cocktail_planning import StaticCocktailPlanning


class CocktailManagement:

    def __init__(
        self,
        cocktail_persistence: CocktailBarStatePersistence,
        cocktail_system: CocktailSystem,
        planning: StaticCocktailPlanning,
    ):
        self._persistence_ = cocktail_persistence
        self._system_ = cocktail_system
        self._planning_ = planning
        self._old_system_state_ = cocktail_system.get_state()

    def check_update(self):
        new_system_state = self._system_.get_state()

        if new_system_state.plan_progress != self._old_system_state_.plan_progress:
            plan_progression_events = self._planning_.get_consequences(
                prior_plan_progress=self._old_system_state_.plan_progress,
                current_plan_progress=new_system_state.plan_progress,
            )
            self._persistence_.persist_events(plan_progression_events)

        bar_state = self._persistence_.get_current_state()
        if new_system_state.status == CocktailSystemStatus.idle:
            order_queue = bar_state.order_queue
            if order_queue:
                next_order_id = order_queue[0]
                next_order = bar_state.orders[next_order_id]
                assert next_order.status == OrderStatus.enqueued
                recipe = bar_state.recipes[next_order.recipe_id]
                plan = self._planning_.plan_cocktail(recipe, new_system_state)
                self._system_.run_plan(plan)
