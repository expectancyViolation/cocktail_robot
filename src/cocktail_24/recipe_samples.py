from cocktail_24.cocktail_recipes import IngredientId, CocktailRecipe, CocktailRecipeStep, \
    CocktailRecipeAddIngredient


class TypicalIngredients:
    whiskey = IngredientId("whiskey")
    vodka = IngredientId("vodka")
    gin = IngredientId("gin")
    tequila = IngredientId("tequila")


class SampleRecipes:

    @staticmethod
    def the_vomit() -> CocktailRecipe:
        return CocktailRecipe(
            title="the_vomit",
            steps=(
                # CocktailRecipeStep(
                #     step_title="pour whiskey and gin",
                #     instructions={
                #         CocktailRecipeAddIngredient(ingredient=TypicalIngredients.whiskey, amount_in_ml=40),
                #         CocktailRecipeAddIngredient(ingredient=TypicalIngredients.gin, amount_in_ml=60),
                #     }
                # ),
                CocktailRecipeStep(
                    step_title="add some tequila",
                    instructions={
                        CocktailRecipeAddIngredient(ingredient=TypicalIngredients.tequila, amount_in_ml=100)
                    }
                ),

            )
        )
