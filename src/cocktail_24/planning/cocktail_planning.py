import uuid
from collections import defaultdict
from typing import Protocol, Sequence

from cocktail_24.cocktail.cocktail_bookkeeping import (
    CocktailBarEvent,
    SlotStatus,
    SlotPath,
    AmountPouredEvent,
)
from cocktail_24.cocktail.cocktail_recipes import CocktailRecipe
from cocktail_24.cocktail_robo import (
    CocktailRobotZapfTask,
    CocktailRobotPumpTask,
    CocktailPosition,
)
from cocktail_24.cocktail_system import (
    CocktailSystemState,
    PlanProgress,
    CocktailSystemPlan,
)
from cocktail_24.planning.cocktail_planner import (
    CocktailSystemConfig,
    CocktailZapfStationConfig,
    CocktailPumpStationConfig,
    SimpleRobotMotionPlanner,
    SimpleRobotIngredientPlanner,
    SimpleRobotIngredientPlannerConfig,
    DefaultRecipeCocktailPlanner,
    SlotAmounts,
    IngredientAmounts,
    CocktailPlanner,
    RobotMotionPlanner,
    RobotIngredientPlanner,
)
from cocktail_24.recipe_samples import TypicalIngredients, SampleRecipes


class RecipeCocktailPlannerFactory(Protocol):

    def get_planner(
        self,
        recipe: CocktailRecipe,
        slots_status: Sequence[SlotStatus],
        robot_position: CocktailPosition,
        shaker_empty: bool,
    ) -> CocktailPlanner: ...


class DefaultRecipeCocktailPlannerFactory(RecipeCocktailPlannerFactory):

    def __init__(
        self,
        system_config: CocktailSystemConfig,
        motion_planner: RobotMotionPlanner,
        ingredient_planner: RobotIngredientPlanner,
    ):
        self._system_config_ = system_config
        self._motion_planner_ = motion_planner
        self._ingredient_planner_ = ingredient_planner

    def get_planner(
        self,
        recipe: CocktailRecipe,
        slots_status: Sequence[SlotStatus],
        robot_position: CocktailPosition,
        shaker_empty: bool,
    ) -> CocktailPlanner:
        return DefaultRecipeCocktailPlanner(
            system_config=self._system_config_,
            motion_planner=self._motion_planner_,
            ingredient_planner=self._ingredient_planner_,
            recipe=recipe,
            shaker_empty=shaker_empty,
            robot_position=robot_position,
            slots_status=slots_status,
        )


class StaticCocktailPlanning(Protocol):

    def plan_cocktail(
        self,
        recipe: CocktailRecipe,
        slots_status: Sequence[SlotStatus],
        robot_position: CocktailPosition,
        shaker_empty: bool,
    ) -> CocktailSystemPlan: ...

    def get_consequences(
        self,
        system_config: CocktailSystemConfig,
        prior_plan_progress: PlanProgress,
        current_plan_progress: PlanProgress,
    ) -> tuple[CocktailBarEvent, ...]: ...


class DefaultStaticCocktailPlanning(StaticCocktailPlanning):

    def __init__(self, planner_factory: RecipeCocktailPlannerFactory):
        self.planner_factory = planner_factory

    def plan_cocktail(
        self,
        recipe: CocktailRecipe,
        slots_status: Sequence[SlotStatus],
        robot_position: CocktailPosition,
        shaker_empty: bool,
    ) -> CocktailSystemPlan:
        planner = self.planner_factory.get_planner(
            recipe, slots_status, robot_position, shaker_empty
        )
        steps = tuple([*planner.gen_plan_pour_cocktail()])
        plan = CocktailSystemPlan(plan_uuid=uuid.uuid4(), steps=steps)
        return plan

    def get_consequences(
        self,
        system_config: CocktailSystemConfig,
        prior_plan_progress: PlanProgress,
        current_plan_progress: PlanProgress,
    ) -> tuple[CocktailBarEvent, ...]:
        plan = prior_plan_progress.plan
        assert plan == current_plan_progress.plan
        poured = defaultdict(lambda: 0)
        for finished_step in range(
            prior_plan_progress.finished_step_pos + 1,
            current_plan_progress.finished_step_pos + 1,
        ):
            match plan.steps[finished_step]:
                case CocktailRobotZapfTask(slot):
                    slot_path = SlotPath(
                        station_id=system_config.zapf_config.zapf_station_id,
                        slot_id=slot,
                    )
                    poured[slot_path] += system_config.zapf_config.ml_per_zapf
                    pass
                case CocktailRobotPumpTask(durations_in_s=durations):
                    for slot_id, duration in enumerate(durations):
                        if duration > 0.01:
                            slot_path = SlotPath(
                                station_id=system_config.pump_config.pump_station_id,
                                slot_id=slot_id,
                            )
                            poured[slot_path] += (
                                system_config.pump_config.ml_per_second * duration
                            )

        return tuple(
            [
                AmountPouredEvent(slot_path=slot_path, amount_in_ml=amount)
                for slot_path, amount in poured.items()
            ]
        )
