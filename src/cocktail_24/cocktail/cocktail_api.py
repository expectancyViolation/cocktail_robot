import datetime
import pickle
import sqlite3
import uuid
from typing import Protocol, Iterable

# from dataclasses import dataclass
from pydantic.dataclasses import dataclass

from cocktail_24.cocktail.cocktail_bookkeeping import (
    CocktailBarEvent,
    CocktailBarState,
    RecipeCreatedEvent,
    OrderId,
    UserId,
    OrderPlacedEvent,
    OrderCancelledEvent,
    QueuePurgedEvent,
    OrderEnqueuedEvent,
    SlotStatus,
    SlotRefilledEvent,
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
        print(f"in mem initialized {self._state_}")
        self._events_ = []

    def persist_events(self, occurences: Iterable[EventOccurrence]) -> None:
        new_events = [(occ.timestamp, occ.event) for occ in occurences]
        self._events_ += new_events
        self._state_ = CocktailBarState.apply_events(new_events, self._state_)
        # print(f"in mem persisted {self._state_}")

    def get_current_state(self):
        # DANGER RETURNING MUTABLE REFERENCE. DO NOT TOUCH MUTATE
        return self._state_


# TODO this class is a quite generic event recorder and not cocktail related
class SqliteCocktailBarStatePersistence(CocktailBarStatePersistence):

    def __init__(self, sqlite_file: str):
        # pass through to fill None
        self._con_ = sqlite3.connect(sqlite_file)
        self._con_.execute("CREATE TABLE IF NOT EXISTS events (data BLOB)")

        self._state_ = self._load_events_()

    def _load_events_(self) -> CocktailBarState:
        events = [
            pickle.loads(row[0])
            for row in self._con_.execute("SELECT * FROM events").fetchall()
        ]
        return CocktailBarState.apply_events(events, None)

    def _store_events_(
        self, events: list[tuple[datetime.datetime, CocktailBarEvent]]
    ) -> None:
        data = [[pickle.dumps(event)] for event in events]
        self._con_.executemany("INSERT INTO events VALUES(?)", data)
        self._con_.commit()

    def persist_events(self, occurences: Iterable[EventOccurrence]) -> None:
        occurences = [*occurences]
        new_events = [(occ.timestamp, occ.event) for occ in occurences]
        self._store_events_(new_events)
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

    def place_order(self, recipe_id: RecipeId, order_id: OrderId):
        current_state = self._state_persistence_.get_current_state()
        user_id = UserId(uuid.uuid4())
        assert recipe_id in current_state.recipes
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

    def enqueue_order(self, order_id: OrderId):
        self._state_persistence_.persist_events(
            [
                EventOccurrence(
                    event=OrderEnqueuedEvent(order_id=order_id),
                    timestamp=self._get_current_time_(),
                )
            ]
        )

    def refill_slot(self, status: SlotStatus):
        self._state_persistence_.persist_events(
            [
                EventOccurrence(
                    event=SlotRefilledEvent(new_status=status),
                    timestamp=self._get_current_time_(),
                )
            ]
        )
