import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import NewType

IngredientId = NewType("IngredientId", str)


@dataclass(frozen=True)
class IngredientAmount:
    ingredient: IngredientId
    amount_in_ml: float


@dataclass(frozen=True)
class CocktailRecipeAddIngredients:
    to_add: tuple[IngredientAmount, ...]


@dataclass(frozen=True)
class CocktailRecipeShake:
    shake_duration_in_s: float


CocktailRecipeStepInstruction = CocktailRecipeShake | CocktailRecipeAddIngredients


@dataclass(frozen=True)
class CocktailRecipeStep:
    step_title: str
    instruction: CocktailRecipeStepInstruction


RecipeId = NewType("RecipeId", uuid.UUID)


@dataclass(frozen=True)
class CocktailRecipe:
    recipe_id: RecipeId
    title: str
    steps: tuple[CocktailRecipeStep, ...]
