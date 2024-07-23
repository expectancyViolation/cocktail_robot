import uuid
from collections import defaultdict
from functools import reduce
from typing import NewType

from pydantic.dataclasses import dataclass

IngredientId = NewType("IngredientId", str)


@dataclass(frozen=True)
class IngredientAmount:
    ingredient: IngredientId
    amount_in_ml: float


@dataclass(frozen=True)
class IngredientAmounts:
    amounts: tuple[IngredientAmount, ...]

    @staticmethod
    def no_amounts() -> "IngredientAmounts":
        return IngredientAmounts(amounts=tuple())

    # remove duplicates and sort
    def normalize(
        self,
    ) -> "IngredientAmounts":
        lookup = defaultdict(lambda: 0)
        for ia in self.amounts:
            lookup[ia.ingredient] += ia.amount_in_ml
        return IngredientAmounts(
            amounts=tuple(
                sorted(
                    (
                        IngredientAmount(ingredient=ing, amount_in_ml=amount)
                        for ing, amount in lookup.items()
                    ),
                    key=lambda ia_: ia_.ingredient,
                )
            )
        )

    def _neg_(self):
        res = IngredientAmounts(
            amounts=tuple(
                [
                    IngredientAmount(
                        amount_in_ml=-ia.amount_in_ml, ingredient=ia.ingredient
                    )
                    for ia in self.amounts
                ]
            )
        )
        return res.normalize()

    def __add__(self, other: "IngredientAmounts") -> "IngredientAmounts":
        res = IngredientAmounts(amounts=self.amounts + other.amounts)
        return res.normalize()

    def __sub__(self, other: "IngredientAmounts") -> "IngredientAmounts":
        return self + other._neg_()

    def __abs__(self):
        return sum(abs(amount.amount_in_ml) for amount in self.amounts)

    def dist(self, other: "IngredientAmounts") -> float:
        return abs(self - other)


@dataclass(frozen=True)
class CocktailRecipeAddIngredients:
    to_add: IngredientAmounts


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

    def get_overall_ingredient_amounts(self) -> IngredientAmounts:
        return reduce(
            lambda x, y: x + y,
            (
                step.instruction.to_add
                for step in self.steps
                if isinstance(step.instruction, CocktailRecipeAddIngredients)
            ),
        )
