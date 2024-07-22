import uuid
from typing import Protocol

from cocktail_24.cocktail.cocktail_bookkeeping import CocktailBarEvent
from cocktail_24.cocktail.cocktail_recipes import CocktailRecipe
from cocktail_24.cocktail_robo import (
    RecipeCocktailPlannerFactory,
    CocktailRobotZapfTask,
    CocktailRobotPumpTask,
)
from cocktail_24.cocktail_system import (
    CocktailSystemState,
    PlanProgress,
    CocktailSystemPlan,
)


class StaticCocktailPlanning(Protocol):

    def plan_cocktail(
        self, recipe: CocktailRecipe, system_state: CocktailSystemState
    ) -> CocktailSystemPlan: ...

    def get_consequences(
        self, prior_plan_progress: PlanProgress, current_plan_progress: PlanProgress
    ) -> tuple[CocktailBarEvent, ...]: ...


class DefaultStaticCocktailPlanning(StaticCocktailPlanning):

    def __init__(self, planner_factory: RecipeCocktailPlannerFactory):
        self.planner_factory = planner_factory

    def plan_cocktail(
        self, recipe: CocktailRecipe, system_state: CocktailSystemState
    ) -> CocktailSystemPlan:
        steps = tuple(
            [*self.planner_factory.get_planner(recipe).gen_plan_pour_cocktail()]
        )
        plan = CocktailSystemPlan(plan_uuid=uuid.uuid4(), steps=steps)
        return plan

    def get_consequences(
        self, prior_plan_progress: PlanProgress, current_plan_progress: PlanProgress
    ) -> tuple[CocktailBarEvent, ...]:
        plan = prior_plan_progress.plan
        assert plan == current_plan_progress.plan
        res = []
        for finished_step in range(
            prior_plan_progress.finished_step_pos + 1,
            current_plan_progress.finished_step_pos + 1,
        ):
            match plan.steps[finished_step]:
                case CocktailRobotZapfTask():
                    pass
                case CocktailRobotPumpTask():
                    pass
