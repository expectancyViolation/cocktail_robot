import math
from collections import defaultdict
import random
from typing import Sequence

from src.cocktail_24.cocktail_recipes import CocktailRecipe, CocktailRecipeAddIngredient
from src.cocktail_24.cocktail_robo import CocktailPlanner, ALLOWED_COCKTAIL_MOVES, CocktailPosition, \
    CocktailRobotMoveTask, CocktailRobotZapfTask, CocktailZapfConfig
from src.cocktail_24.cocktail_robot_interface import CocktailRoboState


class RandomCocktailPlanner(CocktailPlanner):

    def gen_plan_pour_cocktail(self):
        cocktail_nbs: defaultdict[CocktailPosition, set[CocktailPosition]] = defaultdict(lambda: set())
        for x, y in ALLOWED_COCKTAIL_MOVES:
            if y != CocktailPosition.zapf:
                continue
            cocktail_nbs[x].add(y)
            cocktail_nbs[y].add(x)
        curr_state: CocktailRoboState = yield None
        print(f"currstate is {curr_state}")
        next_pos = random.choice([*cocktail_nbs[curr_state.position]])
        while True:
            print(f"planned move {curr_state=} {next_pos=}")
            # TODO what does the planner need to know?
            resp = yield CocktailRobotMoveTask(to_pos=next_pos)
            assert resp is None
            if next_pos is CocktailPosition.zapf:
                slot = random.randint(1, 13)
                amount = random.randint(1, 5)
                for _ in range(amount):
                    resp = yield CocktailRobotZapfTask(slot=slot)
                    assert resp is None

            next_pos = random.choice([*cocktail_nbs[next_pos]])


class RecipeCocktailPlanner(CocktailPlanner):

    def __init__(self, zapf_config: CocktailZapfConfig, recipe: CocktailRecipe):
        self._zapf_config_ = zapf_config
        self._recipe_ = recipe

    def _assign_zapf_slots_(self, ingredients: Sequence[CocktailRecipeAddIngredient]):
        to_do = []
        for add_ingr in ingredients:
            slot = next(slot_index for slot_index, slot_ingr in self._zapf_config_.zapf_slots.items() if
                        slot_ingr == add_ingr.ingredient)
            amount = math.ceil(add_ingr.amount_in_ml / self._zapf_config_.ml_per_zapf)
            to_do.append((slot, amount))
        return to_do

    def _plan_zapf_slot_tour_(self, ingredients: Sequence[CocktailRecipeAddIngredient]):
        to_do = self._assign_zapf_slots_(ingredients)
        # just do it left to right
        to_do.sort()
        return to_do

    def gen_plan_pour_cocktail(self):
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.home)
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.zapf)
        for step in self._recipe_.steps:
            # ignore shakes for now
            add_ingredients = [inst for inst in step.instructions if isinstance(inst, CocktailRecipeAddIngredient)]
            zapf_tour = self._plan_zapf_slot_tour_(add_ingredients)
            for slot, count_ in zapf_tour:
                for _i in range(count_):
                    yield CocktailRobotZapfTask(slot=slot)

        yield CocktailRobotMoveTask(to_pos=CocktailPosition.home)
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.shake)
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.pour)
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.shake)
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.home)
