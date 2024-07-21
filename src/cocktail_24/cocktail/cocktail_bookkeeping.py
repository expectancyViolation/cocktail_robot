import datetime
import uuid
from collections import namedtuple
from dataclasses import dataclass
from typing import NamedTuple

from cocktail_24.cocktail.cocktail_recipes import IngredientId, CocktailRecipe


class SlotPath(NamedTuple):
    station_id: str
    slot_id: int


@dataclass(frozen=True)
class AmountPouredEvent:
    slot_path: SlotPath
    amount_in_ml: float


@dataclass(frozen=True)
class SlotRefilledEvent:
    slot_path: SlotPath
    new_amount_in_ml: float
    ingredient_id: IngredientId


@dataclass(frozen=True)
class DrinkOrderedEvent:
    order_id: uuid.UUID
    recipe: CocktailRecipe
    user_id: str
    order_time: datetime.datetime


@dataclass(frozen=True)
class OrderCancelledEvent:
    order_id: uuid.UUID


@dataclass(frozen=True)
class OrderFulfilledEvent:
    order_id: uuid.UUID


@dataclass
class CocktailBarConfig:
    drink_limit_ml: float


@dataclass
class CocktailBarState:
    pass


@dataclass(frozen=True)
class CocktailZapfStationConfig:
    ml_per_zapf: float
    zapf_slots: dict[int, IngredientId]
