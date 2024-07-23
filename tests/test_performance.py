import datetime
import os
import random
import tempfile
import time
import uuid
from itertools import islice

from cocktail_24.cocktail.cocktail_api import (
    SqliteCocktailBarStatePersistence,
    EventOccurrence,
)
from cocktail_24.cocktail.cocktail_bookkeeping import (
    OrderPlacedEvent,
    RecipeCreatedEvent,
    UserId,
    SlotStatus,
    SlotPath,
)
from cocktail_24.cocktail.cocktail_recipes import IngredientAmounts
from cocktail_24.cocktail.openai_recipes import get_openai_recipes
from cocktail_24.cocktail_robo import CocktailPosition
from configure import configure_system_config, configure_planning


def gen_dummy_events():
    drinks = get_openai_recipes()
    for drink in drinks:
        yield RecipeCreatedEvent(drink, UserId(uuid.uuid4()))
    while True:
        for drink in drinks:
            yield OrderPlacedEvent(
                order_id=uuid.uuid4(),
                recipe_id=drink.recipe_id,
                user_id=UserId(uuid.uuid4()),
            )


def test_sqlite_persistence():
    with tempfile.TemporaryDirectory() as tempdir:
        filename = os.path.join(tempdir, "test.db")
        filename = "/tmp/test.db"
        persistence = SqliteCocktailBarStatePersistence(filename)

        events = [
            EventOccurrence(event=ev, timestamp=datetime.datetime.now())
            for ev in islice(gen_dummy_events(), 100000)
        ]
        started = time.time()
        persistence.persist_events(events)
        print(f"took {time.time()-started}")


def test_planner_performance():

    drinks = get_openai_recipes()

    amounts = IngredientAmounts.no_amounts()
    for drink in drinks:
        amounts += drink.get_overall_ingredient_amounts()

    slots = [
        SlotStatus(
            slot_path=SlotPath(station_id="zapf", slot_id=random.randint(1, 1000000)),
            ingredient_id=amount.ingredient,
            available_amount_in_ml=amount.amount_in_ml,
        )
        for amount in amounts.amounts
    ]

    planning = configure_planning(system_config=configure_system_config())

    for drink in drinks:
        started = time.time()
        for _ in range(1000):
            plan = planning.plan_cocktail(
                drink, slots, robot_position=CocktailPosition.pump, shaker_empty=True
            )
        print(f"took {time.time()-started}")
