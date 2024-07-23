import random
import uuid

from cocktail_24.cocktail.cocktail_bookkeeping import (
    RecipeCreatedEvent,
    UserId,
    OrderPlacedEvent,
    SlotStatus,
    SlotPath,
    SlotRefilledEvent,
    OrderEnqueuedEvent,
    OrderId,
)
from cocktail_24.cocktail.cocktail_recipes import IngredientAmounts
from cocktail_24.cocktail.openai_recipes import get_openai_recipes


def gen_dummy_events():
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

    for slot in slots:
        yield SlotRefilledEvent(slot)

    for drink in drinks:
        yield RecipeCreatedEvent(drink, UserId(uuid.uuid4()))
    for i in range(100000):
        for drink in drinks:
            order_id = uuid.uuid4()
            yield OrderPlacedEvent(
                order_id=OrderId(order_id),
                recipe_id=drink.recipe_id,
                user_id=UserId(uuid.uuid4()),
            )

            if i % 763 == 0:
                yield OrderEnqueuedEvent(OrderId(order_id))
