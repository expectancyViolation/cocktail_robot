import datetime
import uuid
from dataclasses import dataclass
from typing import Protocol, Iterable

from cocktail_24.cocktail.cocktail_bookkeeping import (
    CocktailBarEvent,
    CocktailBarState,
    RecipeCreatedEvent,
    OrderId,
    UserId,
    OrderPlacedEvent,
    OrderCancelledEvent,
    QueuePurgedEvent,
)
from cocktail_24.cocktail.cocktail_recipes import CocktailRecipe, RecipeId


@dataclass(frozen=True)
class EventOccurrence:
    event: CocktailBarEvent
    timestamp: datetime.datetime


class CocktailBarStatePersistence(Protocol):

    def persist_events(self, occurences: Iterable[EventOccurrence]) -> None: ...

    def get_current_state(self) -> CocktailBarState: ...

    # TODO
    # def snapshot(self):
    #     ...


class InMemoryCocktailBarStatePersistence(CocktailBarStatePersistence):

    def __init__(self, initial_state: CocktailBarState | None = None):
        # pass through to fill None
        self._state_ = CocktailBarState.apply_events([], initial_state)
        self._events_ = []

    def persist_events(self, occurences: Iterable[EventOccurrence]) -> None:
        new_events = [*occurences]
        self._events_ += new_events
        self._state_ = CocktailBarState.apply_events(new_events, self._state_)

    def get_current_state(self):
        # DANGER RETURNING MUTABLE REFERENCE. DO NOT TOUCH MUTATE
        return self._state_


class CocktailApi:

    def __init__(self, state_persistence: CocktailBarStatePersistence):
        self._state_persistence_ = state_persistence

    def _get_current_time_(self):
        return datetime.datetime.now()

    def create_recipe(
        self,
        recipe: CocktailRecipe,
    ):
        current_state = self._state_persistence_.get_current_state()
        user_id = UserId(uuid.uuid4())
        assert recipe.recipe_id not in current_state.recipes
        created_event = RecipeCreatedEvent(recipe=recipe, creator_user_id=user_id)
        self._state_persistence_.persist_events(
            [EventOccurrence(event=created_event, timestamp=self._get_current_time_())]
        )

    def place_order(self, recipe_id: RecipeId) -> OrderId:
        current_state = self._state_persistence_.get_current_state()
        user_id = UserId(uuid.uuid4())
        assert recipe_id in current_state.recipes
        order_id = OrderId(uuid.uuid4())
        order_placed_event = OrderPlacedEvent(
            order_id=order_id, recipe_id=recipe_id, user_id=user_id
        )
        self._state_persistence_.persist_events(
            [
                EventOccurrence(
                    event=order_placed_event, timestamp=self._get_current_time_()
                )
            ]
        )

    def cancel_order(self, order_id: OrderId):
        current_state = self._state_persistence_.get_current_state()

        assert order_id in current_state.orders
        order_cancelled_event = OrderCancelledEvent(order_id=order_id)
        self._state_persistence_.persist_events(
            [
                EventOccurrence(
                    event=order_cancelled_event, timestamp=self._get_current_time_()
                )
            ]
        )

    def purge_queue(self):
        self._state_persistence_.persist_events(
            [
                EventOccurrence(
                    event=QueuePurgedEvent(), timestamp=self._get_current_time_()
                )
            ]
        )
