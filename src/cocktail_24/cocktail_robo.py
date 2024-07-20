from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Generator, List

from src.cocktail_24.cocktail_recipes import IngredientId


class CocktailPosition(Enum):
    home = 1
    zapf = 2
    shake = 3
    pour = 4
    clean = 5
    pump = 6


ALLOWED_COCKTAIL_MOVES = (
    (CocktailPosition.home, CocktailPosition.zapf),
    (CocktailPosition.home, CocktailPosition.shake),
    (CocktailPosition.home, CocktailPosition.clean),
    (CocktailPosition.home, CocktailPosition.pump),
    (CocktailPosition.shake, CocktailPosition.pour)
)


@dataclass(frozen=True)
class CocktailRobotMoveTask:
    to_pos: CocktailPosition


@dataclass(frozen=True)
class CocktailRobotZapfTask:
    slot: int


@dataclass(frozen=True)
class CocktailRobotShakeTask:
    num_shakes: int

# pumping can be parallel
@dataclass(frozen=True)
class CocktailRobotPumpTask:
    durations_in_s: dict[int, float]  # slot to time in s


CocktailRobotTask = CocktailRobotMoveTask | CocktailRobotShakeTask | CocktailRobotZapfTask | CocktailRobotPumpTask


@dataclass(frozen=True)
class CocktailZapfConfig:
    ml_per_zapf: float
    zapf_slots: dict[int, IngredientId]
    cup_limit_in_ml: float


class CocktailPlanner(Protocol):

    def gen_plan_pour_cocktail(self) -> Generator[CocktailRobotTask | None, None, bool]:
        ...
