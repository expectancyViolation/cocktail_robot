from dataclasses import dataclass
from typing import NewType

IngredientId = NewType('IngredientId', str)


@dataclass(frozen=True)
class CocktailRecipeAddIngredient:
    ingredient: IngredientId
    amount_in_ml: float


@dataclass(frozen=True)
class CocktailRecipeShake:
    shake_duration_in_s: float


CocktailRecipeInstruction = CocktailRecipeShake | CocktailRecipeAddIngredient


@dataclass(frozen=True)
class CocktailRecipeStep:
    step_title: str
    instructions: set[CocktailRecipeInstruction]


@dataclass(frozen=True)
class CocktailRecipe:
    title: str
    steps: tuple[CocktailRecipeStep, ...]
