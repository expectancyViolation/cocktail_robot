from src.cocktail_24.cocktail_planning import RecipeCocktailPlanner
from src.cocktail_24.cocktail_robo import CocktailZapfConfig
from src.cocktail_24.recipe_samples import TypicalIngredients, SampleRecipes


def get_the_vomit_planner():
    zapf_config = CocktailZapfConfig(
        ml_per_zapf=20,
        zapf_slots={0: TypicalIngredients.gin, 4: TypicalIngredients.vodka, 7: TypicalIngredients.tequila,
                    11: TypicalIngredients.whiskey},
        cup_limit_in_ml=250
    )

    the_vomit = SampleRecipes.the_vomit()

    planner = RecipeCocktailPlanner(zapf_config=zapf_config, recipe=the_vomit)
    return planner


def test_simple_planner():
    planner = get_the_vomit_planner()

    for step in planner.gen_plan_pour_cocktail():
        print(f"step:{step}")
