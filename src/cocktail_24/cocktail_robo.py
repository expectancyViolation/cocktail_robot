from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Generator, Sequence

from cocktail_24.cocktail.cocktail_bookkeeping import SlotStatus
from cocktail_24.cocktail.cocktail_recipes import CocktailRecipe


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
    (CocktailPosition.shake, CocktailPosition.pour),
    (CocktailPosition.clean, CocktailPosition.pump),
)

ALLOWED_COCKTAIL_MOVES += tuple([(y, x) for x, y in ALLOWED_COCKTAIL_MOVES])


@dataclass(frozen=True)
class CocktailRobotMoveTask:
    to_pos: CocktailPosition


@dataclass(frozen=True)
class CocktailRobotZapfTask:
    slot: int


@dataclass(frozen=True)
class CocktailRobotShakeTask:
    num_shakes: int


@dataclass(frozen=True)
class CocktailRobotPourTask: ...


@dataclass(frozen=True)
class CocktailRobotCleanTask: ...


# pumping can be parallel
@dataclass(frozen=True)
class CocktailRobotPumpTask:
    durations_in_s: list[float]  # slot to time in s


CocktailRobotTask = (
    CocktailRobotMoveTask
    | CocktailRobotShakeTask
    | CocktailRobotZapfTask
    | CocktailRobotPumpTask
    | CocktailRobotPourTask
    | CocktailRobotCleanTask
)
