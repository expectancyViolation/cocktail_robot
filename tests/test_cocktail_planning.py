from cocktail_24.cocktail.cocktail_bookkeeping import SlotStatus, SlotPath
from cocktail_24.cocktail_robo import CocktailPosition
from cocktail_24.planning.cocktail_planner import (
    CocktailSystemConfig,
    CocktailZapfStationConfig,
    CocktailPumpStationConfig,
    SimpleRobotMotionPlanner,
    SimpleRobotIngredientPlanner,
    SimpleRobotIngredientPlannerConfig,
    SlotAmounts,
    IngredientAmounts,
    DefaultRecipeCocktailPlanner,
)
from cocktail_24.recipe_samples import TypicalIngredients, SampleRecipes
from main import configure_initial_state


def test_robot_planning():
    system_config = CocktailSystemConfig(
        zapf_config=CocktailZapfStationConfig(ml_per_zapf=30.0, zapf_station_id="zapf"),
        pump_config=CocktailPumpStationConfig(
            ml_per_second=16.0, pump_station_id="pump"
        ),
        single_shake_duration_in_s=2.0,
    )

    motion_planner = SimpleRobotMotionPlanner()
    ingredient_planner = SimpleRobotIngredientPlanner(
        config=SimpleRobotIngredientPlannerConfig(system_config=system_config)
    )

    initial_state = configure_initial_state()

    robot_position = CocktailPosition.home
    shaker_empty = True

    recipe = SampleRecipes.the_vomit()

    step1_planned = ingredient_planner.plan_ingredients(
        available_slot_amounts=SlotAmounts.from_slots(initial_state.slots),
        amounts=IngredientAmounts.from_recipe_add(recipe.steps[0].instruction),
    )
    print(step1_planned)

    planner = DefaultRecipeCocktailPlanner(
        system_config=system_config,
        recipe=recipe,
        motion_planner=motion_planner,
        ingredient_planner=ingredient_planner,
        slots_status=initial_state.slots,
        robot_position=robot_position,
        shaker_empty=shaker_empty,
    )

    plan = planner.gen_plan_pour_cocktail()
    steps = [*plan]
    print("-----")
    for step in steps:
        print(step)
    # print(plan)
