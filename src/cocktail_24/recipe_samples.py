import uuid

from cocktail_24.cocktail.cocktail_recipes import (
    IngredientId,
    CocktailRecipe,
    CocktailRecipeStep,
    RecipeId,
    IngredientAmount,
    CocktailRecipeAddIngredients,
)


class TypicalIngredients:
    whiskey = IngredientId("whiskey")
    vodka = IngredientId("vodka")
    gin = IngredientId("gin")
    tequila = IngredientId("tequila")


class SampleRecipes:

    @staticmethod
    def the_vomit() -> CocktailRecipe:
        return CocktailRecipe(
            recipe_id=RecipeId(uuid.uuid4()),
            title="the_vomit",
            steps=(
                CocktailRecipeStep(
                    step_title="pour whiskey and gin",
                    instruction=CocktailRecipeAddIngredients(
                        (
                            IngredientAmount(
                                ingredient=TypicalIngredients.whiskey, amount_in_ml=40
                            ),
                            IngredientAmount(
                                ingredient=TypicalIngredients.gin, amount_in_ml=40
                            ),
                        )
                    ),
                ),
                CocktailRecipeStep(
                    step_title="add tequila and vodka",
                    instruction=CocktailRecipeAddIngredients(
                        (
                            IngredientAmount(
                                ingredient=TypicalIngredients.tequila, amount_in_ml=120
                            ),
                            IngredientAmount(
                                ingredient=TypicalIngredients.vodka, amount_in_ml=120
                            ),
                        )
                    ),
                ),
            ),
        )
