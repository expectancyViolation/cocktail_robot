import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence, Protocol

from cocktail_24.cocktail.cocktail_bookkeeping import SlotStatus
from cocktail_24.cocktail.cocktail_recipes import (
    CocktailRecipe,
    IngredientId,
    CocktailRecipeStep,
    CocktailRecipeShake,
    CocktailRecipeAddIngredients,
    IngredientAmount,
)
from cocktail_24.cocktail_robo import (
    CocktailPlanner,
    CocktailPosition,
    CocktailRobotMoveTask,
    RecipeCocktailPlannerFactory,
    CocktailRobotPumpTask,
    CocktailRobotPourTask,
    CocktailRobotShakeTask,
)
from cocktail_24.cocktail_robot_interface import CocktailRoboState
from cocktail_24.cocktail_system import CocktailSystemStatus
from cocktail_24.pump_interface.pump_interface import PumpStatus


@dataclass(frozen=True)
class CocktailZapfStationConfig:
    ml_per_zapf: float
    zapf_slots: dict[int, IngredientId]
    zapf_station_id: str


@dataclass(frozen=True)
class CocktailPumpStationConfig:
    ml_per_second: float
    zapf_slots: dict[int, IngredientId]
    pump_station_id: str


class CocktailSystemConfig:
    zapf_config: CocktailZapfStationConfig
    pump_config: CocktailPumpStationConfig
    single_shake_duration_in_s: float


class RobotMotionPlanner(Protocol):

    def plan_move(self, from_pos: CocktailPosition, to_pos: CocktailPosition): ...


SlotLookup = dict[str, dict[int, IngredientAmount]]


@dataclass(frozen=True)
class IngredientAmounts:
    amounts: tuple[IngredientAmount, ...]

    # remove duplicates and sort
    def normalize(
        self,
    ) -> "IngredientAmounts":
        lookup = defaultdict(lambda: 0)
        for ia in self.amounts:
            lookup[ia.ingredient] += ia.amount_in_ml
        return IngredientAmounts(
            amounts=tuple(
                sorted(
                    (
                        IngredientAmount(ingredient=ing, amount_in_ml=amount)
                        for ing, amount in lookup.items()
                    ),
                    key=lambda ia: ia.ingredient,
                )
            )
        )

    def _neg_(self):
        res = IngredientAmounts(
            amounts=tuple(
                [
                    IngredientAmount(
                        amount_in_ml=-ia.amount_in_ml, ingredient=ia.ingredient
                    )
                    for ia in self.amounts
                ]
            )
        )
        return res.normalize()

    def __add__(self, other: "IngredientAmounts") -> "IngredientAmounts":
        res = IngredientAmounts(amounts=self.amounts + other.amounts)
        return res.normalize()

    def __sub__(self, other: "IngredientAmounts") -> "IngredientAmounts":
        return self + other._neg_()

    def __abs__(self):
        return sum(abs(amount.amount_in_ml) for amount in self.amounts)

    def dist(self, other: "IngredientAmounts") -> float:
        return abs(self - other)


@dataclass(frozen=True)
class SlotAmounts:
    slots_lookup: SlotLookup

    def is_valid(self):
        return all(
            slot_amount.amount_in_ml > -0.001
            for station in self.slots_lookup.values()
            for slot_amount in station.values()
        )

    def __sub__(self, other):
        resulting_amounts = {
            station_id: {slot_id: amount}
            for station_id, station in self.slots_lookup.items()
            for slot_id, amount in station.values()
        }
        return SlotAmounts(slots_lookup=resulting_amounts)

    def to_ingredient_amounts(self):
        amounts = tuple(
            [
                amount
                for station in self.slots_lookup.values()
                for amount in station.values()
            ]
        )
        return IngredientAmounts(amounts=amounts).normalize()


@dataclass(frozen=True)
class IngredientPlan:
    amounts: SlotAmounts

    could_fulfill: bool  # missed target?
    badness: float = 0.0  # target missed by how much
    cost: float = 0.0


class RobotIngredientPlanner(Protocol):

    def plan_ingredients(
        self, available_slot_amounts: SlotAmounts, amounts: IngredientAmounts
    ) -> IngredientPlan: ...


@dataclass(frozen=True)
class SimpleRobotIngredientPlannerConfig:
    system_config: CocktailSystemConfig


class SimpleRobotIngredientPlanner(RobotIngredientPlanner):

    minimum_amount_in_ml = 0.2
    slop_in_ml = 0.2

    def __init__(self, config: SimpleRobotIngredientPlannerConfig):
        self._config_ = config

    def plan_ingredients(
        self, available_slot_amounts: SlotAmounts, amounts: IngredientAmounts
    ) -> IngredientPlan:
        pump_station_id = self._config_.system_config.pump_config.pump_station_id
        zapf_station_id = self._config_.system_config.zapf_config.zapf_station_id
        plans = {pump_station_id: {}, zapf_station_id: {}}
        could_fulfill = True
        badness = 0.0
        for amount in amounts:
            remaining_amount = amount.amount_in_ml
            # prefer pump over zapf if possible
            for station in ():
                for slot_id, ia in available_slot_amounts.slots_lookup[station].items():
                    if (
                        remaining_amount
                        < SimpleRobotIngredientPlanner.minimum_amount_in_ml
                    ):
                        break
                    if ia.ingredient == amount.ingredient:
                        remove = min(amount.amount_in_ml, ia.amount_in_ml)
                        if remove > SimpleRobotIngredientPlanner.minimum_amount_in_ml:
                            plans[station][slot_id] = remove
                            remaining_amount -= remove
            if remaining_amount > self.minimum_amount_in_ml:
                could_fulfill = False
                badness += remaining_amount
        return IngredientPlan(
            amounts=SlotAmounts(slots_lookup=plans),
            badness=badness,
            could_fulfill=could_fulfill,
        )


class DefaultRecipeCocktailPlanner(CocktailPlanner):

    def __init__(
        self,
        system_config: CocktailSystemConfig,
        recipe: CocktailRecipe,
        motion_planner: RobotMotionPlanner,
        ingredient_planner: RobotIngredientPlanner,
        slots_status: Sequence[SlotStatus],
        robot_position: CocktailPosition,
        shaker_empty: bool,
    ):
        self._system_config_ = system_config
        self._recipe_ = recipe
        self._motion_planner_ = motion_planner
        self._ingredient_planner_ = ingredient_planner

        # TODO DANGER: maybe rather pass this around, since this is mutated ?
        #   we cannot rerun the planner!!
        self._station_slots_amounts_: SlotAmounts = (
            DefaultRecipeCocktailPlanner.get_slot_lookup(slots_status)
        )
        self._robot_position_ = robot_position
        self._shaker_empty_ = shaker_empty

        self._r

    @staticmethod
    def get_slot_lookup(slots: Sequence[SlotStatus]) -> SlotAmounts:
        res: defaultdict[str, dict[int, IngredientAmount]] = defaultdict(dict)
        for slot in slots:
            res[slot.slot_path.station_id][slot.slot_path.slot_id] = IngredientAmount(
                ingredient=slot.ingredient_id, amount_in_ml=slot.available_amount_in_ml
            )
        return SlotAmounts(slots_lookup=res)

    def _assign_zapf_slots_(self, ingredients: Sequence[IngredientAmount]):
        to_do = []
        for add_ingr in ingredients:
            slot = next(
                slot_index
                for slot_index, slot_ingr in self._zapf_config_.zapf_slots.items()
                if slot_ingr == add_ingr.ingredient
            )
            amount = math.ceil(add_ingr.amount_in_ml / self._zapf_config_.ml_per_zapf)
            to_do.append((slot, amount))
        return to_do

    def _plan_zapf_slot_tour_(self, ingredients: Sequence[IngredientAmount]):
        to_do = self._assign_zapf_slots_(ingredients)
        # just do it left to right
        to_do.sort()
        return to_do

    def gen_plan_shake(self, shake_duration_in_s: float):
        yield from self._motion_planner_.plan_move(
            self._robot_position_, CocktailPosition.pump
        )
        self._robot_position_ = CocktailPosition.pump
        num_shakes = math.ceil(
            shake_duration_in_s / self._system_config_.single_shake_duration_in_s
        )
        yield CocktailRobotShakeTask(num_shakes=num_shakes)

    def gen_plan_add_ingredients(self, ingredients: IngredientAmounts):
        ingredient_plan = self._ingredient_planner_.plan_ingredients(
            self._station_slots_amounts_, ingredients
        )

        slot_amounts = self._station_slots_amounts_ - ingredient_plan.amounts
        assert slot_amounts.is_valid()
        planned_ias = slot_amounts.to_ingredient_amounts()
        dist_to_target = ingredients.dist(planned_ias)
        assert dist_to_target < SimpleRobotIngredientPlanner.slop_in_ml

    def gen_pump_ingredients(self, slot_amounts: SlotAmounts):
        pump_amounts = slot_amounts.slots_lookup[
            self._system_config_.pump_config.pump_station_id
        ]
        yield from self._motion_planner_.plan_move(
            self._robot_position_, CocktailPosition.pump
        )
        self._robot_position_ = CocktailPosition.pump

    def gen_plan_recipe_step(self, step: CocktailRecipeStep):
        match step.instruction:
            case CocktailRecipeShake(shake_duration_in_s=duration_in_s):
                yield from self.gen_plan_shake(shake_duration_in_s=duration_in_s)
            case CocktailRecipeAddIngredients():
                normalized = IngredientAmounts(
                    amounts=step.instruction.to_add
                ).normalize()
                yield from self.gen_plan_add_ingredients(normalized)
            case _:
                raise Exception(f"unknown instruction {step.instruction}")

    def gen_plan_pour_cocktail(self):

        yield CocktailRobotMoveTask(to_pos=CocktailPosition.shake)
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.home)
        # yield CocktailRobotShakeTask(num_shakes=5)
        # yield CocktailRobotMoveTask(to_pos=CocktailPosition.home)
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.pump)
        yield CocktailRobotPumpTask(durations_in_s=[5.0, 0.0, 10.0, 0.0])
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.home)
        # yield CocktailRobotMoveTask(to_pos=CocktailPosition.zapf)
        # for step in self._recipe_.steps:
        #     # ignore shakes for now
        #     add_ingredients = [inst for inst in step.instructions if isinstance(inst, CocktailRecipeAddIngredient)]
        #     zapf_tour = self._plan_zapf_slot_tour_(add_ingredients)
        #     for slot, count_ in zapf_tour:
        #         for _i in range(count_):
        #             yield CocktailRobotZapfTask(slot=slot)

        # yield CocktailRobotMoveTask(to_pos=CocktailPosition.home)
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.shake)
        # while True:
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.pour)
        yield CocktailRobotPourTask()
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.shake)
        yield CocktailRobotMoveTask(to_pos=CocktailPosition.home)


class DefaultRecipeCocktailPlannerFactory(RecipeCocktailPlannerFactory):

    def __init__(self, zapf_config: CocktailZapfStationConfig):
        self._zapf_config_ = zapf_config

    def get_planner(self, recipe: CocktailRecipe) -> CocktailPlanner:
        return DefaultRecipeCocktailPlanner(
            zapf_config=self._zapf_config_, recipe=recipe
        )
