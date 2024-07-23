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
from cocktail_24.cocktail.dummy_events import gen_dummy_events
from cocktail_24.cocktail.openai_recipes import get_openai_recipes
from cocktail_24.cocktail_robo import CocktailPosition
from configure import configure_system_config, configure_planning


def test_sqlite_persistence():
    with tempfile.TemporaryDirectory() as tempdir:
        filename = os.path.join(tempdir, "test.db")
        # filename = "/tmp/test.db"
        persistence = SqliteCocktailBarStatePersistence(filename)

        events = [
            EventOccurrence(event=ev, timestamp=datetime.datetime.now())
            for ev in islice(gen_dummy_events(), 100000)
        ]
        started = time.time()
        persistence.persist_events(events)
        print(f"took {time.time()-started}")


# def test_planner_performance():
#
#     drinks = get_openai_recipes()
#
#     planning = configure_planning(system_config=configure_system_config())
#
#     for drink in drinks:
#         started = time.time()
#         for _ in range(1000):
#             _plan = planning.plan_cocktail(
#                 drink, slots, robot_position=CocktailPosition.pump, shaker_empty=True
#             )
#         print(f"took {time.time()-started}")
