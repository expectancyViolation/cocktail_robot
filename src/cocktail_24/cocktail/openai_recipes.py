# Margarita recipe
import uuid

from cocktail_24.cocktail.cocktail_recipes import (
    IngredientAmount,
    IngredientId,
    CocktailRecipeAddIngredients,
    CocktailRecipeShake,
    CocktailRecipe,
    RecipeId,
    CocktailRecipeStep,
)
from cocktail_24.planning.cocktail_planner import IngredientAmounts


def get_openai_recipes():
    margarita_ingredients = (
        IngredientAmount(ingredient=IngredientId("Tequila"), amount_in_ml=50.0),
        IngredientAmount(ingredient=IngredientId("Triple sec"), amount_in_ml=25.0),
        IngredientAmount(ingredient=IngredientId("Lime juice"), amount_in_ml=25.0),
        IngredientAmount(ingredient=IngredientId("Salt"), amount_in_ml=1.0),
    )

    margarita_steps = (
        CocktailRecipeStep(
            step_title="Add Ingredients",
            instruction=CocktailRecipeAddIngredients(
                to_add=IngredientAmounts(amounts=margarita_ingredients)
            ),
        ),
        CocktailRecipeStep(
            step_title="Shake",
            instruction=CocktailRecipeShake(shake_duration_in_s=20.0),
        ),
    )

    margarita_recipe = CocktailRecipe(
        recipe_id=RecipeId(uuid.uuid4()), title="Margarita", steps=margarita_steps
    )

    # Mojito recipe
    mojito_ingredients = (
        IngredientAmount(ingredient=IngredientId("White rum"), amount_in_ml=50.0),
        IngredientAmount(ingredient=IngredientId("Lime juice"), amount_in_ml=25.0),
        IngredientAmount(ingredient=IngredientId("Mint leaves"), amount_in_ml=10.0),
        IngredientAmount(ingredient=IngredientId("Sugar syrup"), amount_in_ml=15.0),
        IngredientAmount(ingredient=IngredientId("Soda water"), amount_in_ml=100.0),
    )

    mojito_steps = (
        CocktailRecipeStep(
            step_title="Add Ingredients",
            instruction=CocktailRecipeAddIngredients(
                to_add=IngredientAmounts(amounts=mojito_ingredients[:-1])
            ),
        ),
        CocktailRecipeStep(
            step_title="Top up with soda water",
            instruction=CocktailRecipeAddIngredients(
                to_add=IngredientAmounts(amounts=(mojito_ingredients[-1],))
            ),
        ),
    )

    mojito_recipe = CocktailRecipe(
        recipe_id=RecipeId(uuid.uuid4()), title="Mojito", steps=mojito_steps
    )

    # Old Fashioned recipe
    old_fashioned_ingredients = (
        IngredientAmount(ingredient=IngredientId("Bourbon"), amount_in_ml=50.0),
        IngredientAmount(ingredient=IngredientId("Sugar cube"), amount_in_ml=1.0),
        IngredientAmount(
            ingredient=IngredientId("Angostura bitters"), amount_in_ml=2.0
        ),
        IngredientAmount(ingredient=IngredientId("Water"), amount_in_ml=10.0),
        IngredientAmount(ingredient=IngredientId("Orange peel"), amount_in_ml=1.0),
    )

    old_fashioned_steps = (
        CocktailRecipeStep(
            step_title="Muddle sugar and bitters",
            instruction=CocktailRecipeAddIngredients(
                to_add=IngredientAmounts(amounts=old_fashioned_ingredients[1:3])
            ),
        ),
        CocktailRecipeStep(
            step_title="Add bourbon",
            instruction=CocktailRecipeAddIngredients(
                to_add=IngredientAmounts(amounts=(old_fashioned_ingredients[0],))
            ),
        ),
    )

    old_fashioned_recipe = CocktailRecipe(
        recipe_id=RecipeId(uuid.uuid4()),
        title="Old Fashioned",
        steps=old_fashioned_steps,
    )

    # Cuba Libre recipe
    cuba_libre_ingredients = (
        IngredientAmount(ingredient=IngredientId("White rum"), amount_in_ml=50.0),
        IngredientAmount(ingredient=IngredientId("Cola"), amount_in_ml=120.0),
        IngredientAmount(ingredient=IngredientId("Lime juice"), amount_in_ml=10.0),
        IngredientAmount(ingredient=IngredientId("Lime wedge"), amount_in_ml=1.0),
    )

    cuba_libre_steps = (
        CocktailRecipeStep(
            step_title="Add rum and lime juice",
            instruction=CocktailRecipeAddIngredients(
                to_add=IngredientAmounts(
                    amounts=(cuba_libre_ingredients[0], cuba_libre_ingredients[2])
                )
            ),
        ),
        CocktailRecipeStep(
            step_title="Top up with cola",
            instruction=CocktailRecipeAddIngredients(
                to_add=IngredientAmounts(amounts=(cuba_libre_ingredients[1],))
            ),
        ),
        CocktailRecipeStep(
            step_title="Garnish with lime wedge",
            instruction=CocktailRecipeAddIngredients(
                to_add=IngredientAmounts(amounts=(cuba_libre_ingredients[3],))
            ),
        ),
    )

    cuba_libre_recipe = CocktailRecipe(
        recipe_id=RecipeId(uuid.uuid4()), title="Cuba Libre", steps=cuba_libre_steps
    )

    return [margarita_recipe, mojito_recipe, old_fashioned_recipe, cuba_libre_recipe]


def test_openai_recipes_are_valid():
    print(get_openai_recipes())
