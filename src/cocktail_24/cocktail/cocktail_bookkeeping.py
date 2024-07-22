import datetime
import logging
import uuid
from enum import Enum
from typing import NewType, Iterable

from pydantic import RootModel
from pydantic.dataclasses import dataclass

from cocktail_24.cocktail.cocktail_recipes import IngredientId, CocktailRecipe, RecipeId
from cocktail_24.recipe_samples import TypicalIngredients, SampleRecipes


# from dataclasses import dataclass

OrderId = NewType("OrderId", uuid.UUID)
UserId = NewType("UserId", uuid.UUID)


class Station:
    zapf = "zapf"
    pump = "pump"


@dataclass(frozen=True)
class SlotPath:
    station_id: str
    slot_id: int


@dataclass(frozen=True)
class AmountPouredEvent:
    slot_path: SlotPath
    amount_in_ml: float


@dataclass(frozen=True)
class SlotStatus:
    slot_path: SlotPath
    available_amount_in_ml: float
    ingredient_id: IngredientId

    def pour(self, amount_in_ml: float) -> "SlotStatus":
        return SlotStatus(
            slot_path=self.slot_path,
            available_amount_in_ml=self.available_amount_in_ml - amount_in_ml,
            ingredient_id=self.ingredient_id,
        )


@dataclass(frozen=True)
class SlotRefilledEvent:
    new_status: SlotStatus


@dataclass(frozen=True)
class OrderPlacedEvent:
    order_id: uuid.UUID
    recipe_id: RecipeId
    user_id: UserId


@dataclass(frozen=True)
class OrderCancelledEvent:
    order_id: uuid.UUID


@dataclass(frozen=True)
class OrderFulfilledEvent:
    order_id: uuid.UUID


@dataclass(frozen=True)
class QueuePurgedEvent:
    pass


@dataclass(frozen=True)
class SnapshotEvent:
    json_data: str


@dataclass(frozen=True)
class RecipeCreatedEvent:
    recipe: CocktailRecipe
    creator_user_id: UserId


CocktailBarEvent = (
    SlotRefilledEvent
    | AmountPouredEvent
    | OrderPlacedEvent
    | OrderFulfilledEvent
    | OrderCancelledEvent
    | QueuePurgedEvent
    | SnapshotEvent
    | RecipeCreatedEvent
)


@dataclass
class CocktailBarConfig:
    drink_limit_ml: float


class OrderStatus(Enum):
    ordered = "ordered"
    cancelled = "cancelled"
    fulfilled = "fulfilled"


@dataclass
class Order:
    order_id: OrderId
    status: OrderStatus
    ordered_by: UserId
    recipe_id: RecipeId
    time_of_order: datetime.datetime


@dataclass
class CocktailBarState:
    order_queue: list[OrderId]
    slots: list[SlotStatus]

    orders: dict[OrderId, Order]

    recipes: dict[RecipeId, CocktailRecipe]

    def handle_refilled(self, refilled: SlotRefilledEvent):
        location = next(
            (
                i
                for i, status in enumerate(self.slots)
                if status.slot_path == refilled.new_status.slot_path
            ),
            None,
        )
        if location is None:
            self.slots += [refilled.new_status]
        else:
            self.slots[location] = refilled.new_status

    def handle_poured(self, poured: AmountPouredEvent):
        location = next(
            (
                i
                for i, status in enumerate(self.slots)
                if status.slot_path == poured.slot_path
            ),
            None,
        )
        if location is None:
            logging.error("registered pour for non-existent slot")
        else:
            self.slots[location].available_amount_in_ml -= poured.amount_in_ml

    def handle_order_placed(
        self, order_placed: OrderPlacedEvent, time_of_event: datetime.datetime
    ):
        if order_placed.order_id not in self.orders:
            # noinspection PyTypeChecker
            self.orders[order_placed.order_id] = Order(
                order_id=order_placed.order_id,
                status=OrderStatus.ordered,
                ordered_by=order_placed.user_id,
                recipe_id=order_placed.recipe_id,
                time_of_order=time_of_event,
            )
        else:
            logging.error((f"tried to readd existing order {order_placed}"))

    @staticmethod
    def apply_events(
        events: Iterable[tuple[datetime.datetime, CocktailBarEvent]],
        initial_state: "CocktailBarState | None" = None,
    ) -> "CocktailBarState":
        if initial_state is None:
            initial_state = CocktailBarState(
                order_queue=[], slots=[], orders={}, recipes={}
            )
        state = initial_state
        for time_of_event, event in events:
            match event:
                case SlotRefilledEvent():
                    state.handle_refilled(event)
                case AmountPouredEvent():
                    state.handle_poured(event)
                case OrderPlacedEvent():
                    state.handle_order_placed(event, time_of_event)
                case OrderFulfilledEvent(order_id=order_id):
                    if order_id in state.orders:
                        state.orders[order_id].status = OrderStatus.fulfilled
                    else:
                        logging.warning((f"tried to mark nonexisting order {event}"))
                case OrderCancelledEvent(order_id=order_id):
                    if order_id in state.orders:
                        state.orders[order_id].status = OrderStatus.cancelled
                    else:
                        logging.warning((f"tried to mark nonexisting order {event}"))
                case RecipeCreatedEvent(recipe=recipe, creator_user_id=_user_id):
                    state.recipes[recipe.recipe_id] = recipe

                case QueuePurgedEvent():
                    state.order_queue = []
                case SnapshotEvent(json_data=_json_data):
                    logging.error("snapshotting not yet implemented")
                case _:
                    logging.error(f"unhandled event in BarState reconstruction {event}")
        return state

    def json_snapshot(self) -> any:
        return RootModel[CocktailBarState](self).model_dump_json(indent=4)

    @staticmethod
    def load_snapshot(json_data: str) -> "CocktailBarState":
        return RootModel[CocktailBarState].model_validate_json(json_data)


def test_can_dump_bar_state():
    events = [
        SlotRefilledEvent(
            new_status=SlotStatus(
                slot_path=SlotPath(slot_id=i, station_id=Station.zapf),
                available_amount_in_ml=700.0,
                ingredient_id=ingredient_id,
            )
        )
        for i, ingredient_id in enumerate(
            (
                TypicalIngredients.tequila,
                TypicalIngredients.whiskey,
                TypicalIngredients.gin,
                TypicalIngredients.vodka,
            )
        )
    ]

    good_order_id = uuid.uuid4()
    mth_id = uuid.uuid4()
    the_vomit = SampleRecipes.the_vomit()
    events += [
        RecipeCreatedEvent(the_vomit, creator_user_id=mth_id),
        OrderPlacedEvent(
            order_id=good_order_id, recipe_id=the_vomit.recipe_id, user_id=mth_id
        ),
        OrderFulfilledEvent(order_id=good_order_id),
    ]

    timed_events = [(datetime.datetime.now(), event) for event in events]

    state = CocktailBarState.apply_events(events=timed_events)
    print(state.json_snapshot())


@dataclass(frozen=True)
class CocktailZapfStationConfig:
    ml_per_zapf: float
    zapf_slots: dict[int, IngredientId]
