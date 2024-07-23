import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence, Protocol, Generator

from cocktail_24.cocktail.cocktail_bookkeeping import SlotStatus
from cocktail_24.cocktail.cocktail_recipes import (
    CocktailRecipe,
    CocktailRecipeStep,
    CocktailRecipeShake,
    CocktailRecipeAddIngredients,
    IngredientAmount,
    IngredientAmounts,
)
from cocktail_24.cocktail_robo import (
    CocktailPosition,
    CocktailRobotMoveTask,
    CocktailRobotPumpTask,
    CocktailRobotShakeTask,
    CocktailRobotZapfTask,
    CocktailRobotTask,
    ALLOWED_COCKTAIL_MOVES,
    CocktailRobotCleanTask,
    CocktailRobotPourTask,
)
from util import get_shortest_path


class CocktailPlanner(Protocol):

    def gen_plan_pour_cocktail(
        self,
    ) -> Generator[CocktailRobotTask | None, None, bool]: ...


@dataclass(frozen=True)
class CocktailZapfStationConfig:
    ml_per_zapf: float
    zapf_station_id: str


@dataclass(frozen=True)
class CocktailPumpStationConfig:
    ml_per_second: float
    pump_station_id: str


@dataclass(frozen=True)
class CocktailSystemConfig:
    zapf_config: CocktailZapfStationConfig
    pump_config: CocktailPumpStationConfig
    single_shake_duration_in_s: float


class RobotMotionPlanner(Protocol):

    def gen_plan_move(self, from_pos: CocktailPosition, to_pos: CocktailPosition): ...


class SimpleRobotMotionPlanner(RobotMotionPlanner):

    def gen_plan_move(self, from_pos: CocktailPosition, to_pos: CocktailPosition):
        # free from machine
        for pos in get_shortest_path(ALLOWED_COCKTAIL_MOVES, from_pos, to_pos):
            yield CocktailRobotMoveTask(to_pos=pos)


SlotLookup = dict[str, dict[int, IngredientAmount]]


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
            for slot_id, amount in station.items()
        }
        return SlotAmounts(slots_lookup=resulting_amounts)

    @staticmethod
    def from_slots(slots: Sequence[SlotStatus]) -> "SlotAmounts":
        res: defaultdict[str, dict[int, IngredientAmount]] = defaultdict(dict)
        for slot in slots:
            # no duplicates
            assert slot.slot_path.slot_id not in res[slot.slot_path.station_id]
            res[slot.slot_path.station_id][slot.slot_path.slot_id] = IngredientAmount(
                ingredient=slot.ingredient_id, amount_in_ml=slot.available_amount_in_ml
            )
        return SlotAmounts(slots_lookup=res)

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


class IngredientsMissingException(Exception):

    def __init__(self, missing_ingredients: IngredientAmounts):
        self._missing_ingredients = missing_ingredients


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
        for amount in amounts.normalize().amounts:
            remaining_amount = amount.amount_in_ml
            # prefer pump over zapf if possible
            for station in (pump_station_id, zapf_station_id):
                for slot_id, ia in available_slot_amounts.slots_lookup[station].items():
                    if (
                        remaining_amount
                        < SimpleRobotIngredientPlanner.minimum_amount_in_ml
                    ):
                        break
                    if ia.ingredient == amount.ingredient:
                        remove = min(amount.amount_in_ml, ia.amount_in_ml)
                        if remove > SimpleRobotIngredientPlanner.minimum_amount_in_ml:
                            plans[station][slot_id] = IngredientAmount(
                                ia.ingredient, remove
                            )
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
    CLEAN_PUMP_SLOT = 0
    CLEAN_PUMP_DURATION_IN_S = 10.0

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
        self._station_slots_amounts_ = SlotAmounts.from_slots(slots_status)
        self._robot_position_ = robot_position
        self._shaker_empty_ = shaker_empty

        self.runlock = False

    def _calculate_zapf_tasks_(
        self, zapf_slot_id: int, amount: IngredientAmount
    ) -> list[CocktailRobotZapfTask]:
        n_zapf = math.ceil(
            amount.amount_in_ml / self._system_config_.zapf_config.ml_per_zapf
        )
        return [CocktailRobotZapfTask(slot=zapf_slot_id) for _ in range(n_zapf)]

    def _calculate_pump_task_(
        self, pump_slots: dict[int, IngredientAmount]
    ) -> CocktailRobotPumpTask:
        durations = [0.0] * 4
        for slot_id, amount in pump_slots.items():
            durations[slot_id] = (
                amount.amount_in_ml / self._system_config_.pump_config.ml_per_second
            )
        return CocktailRobotPumpTask(durations)

    def gen_plan_shake(self, shake_duration_in_s: float):
        yield from self._motion_planner_.gen_plan_move(
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
        logging.info("planned ingredients %s", ingredient_plan)

        remaining_station_amounts = (
            self._station_slots_amounts_ - ingredient_plan.amounts
        )
        assert remaining_station_amounts.is_valid()
        planned_ias = ingredient_plan.amounts.to_ingredient_amounts()
        missing_ingredients = ingredients - planned_ias
        missing_amount = abs(missing_ingredients)

        # TODO: missing might be negative on wrong plan!
        assert all(
            x.amount_in_ml > -SimpleRobotIngredientPlanner.slop_in_ml
            for x in missing_ingredients.amounts
        )
        if missing_amount > SimpleRobotIngredientPlanner.slop_in_ml:
            raise IngredientsMissingException(missing_ingredients)

        yield from self.gen_pump_ingredients(ingredient_plan.amounts)
        yield from self.gen_zapf_ingredients(ingredient_plan.amounts)

    def gen_zapf_ingredients(self, slot_amounts: SlotAmounts):
        zapf_amounts = slot_amounts.slots_lookup[
            self._system_config_.zapf_config.zapf_station_id
        ]
        need_zapf = any(
            val.amount_in_ml > SimpleRobotIngredientPlanner.minimum_amount_in_ml
            for val in zapf_amounts.values()
        )
        if need_zapf:
            yield from self._motion_planner_.gen_plan_move(
                self._robot_position_, CocktailPosition.zapf
            )
            self._robot_position_ = CocktailPosition.zapf
            for slot_id, zapf_amount in zapf_amounts.items():
                if (
                    zapf_amount.amount_in_ml
                    <= SimpleRobotIngredientPlanner.minimum_amount_in_ml
                ):
                    logging.warning(
                        f"skipping zapf of {zapf_amount=} (too little to zapf)"
                    )
                for zapf in self._calculate_zapf_tasks_(slot_id, zapf_amount):
                    yield zapf

    def gen_pump_ingredients(self, slot_amounts: SlotAmounts):
        pump_station_id = self._system_config_.pump_config.pump_station_id
        if pump_station_id not in slot_amounts.slots_lookup:
            logging.warning("no need pump (skipping) noexist")
            return
        pump_amounts = slot_amounts.slots_lookup[
            self._system_config_.pump_config.pump_station_id
        ]
        need_pump = any(
            val.amount_in_ml > SimpleRobotIngredientPlanner.minimum_amount_in_ml
            for val in pump_amounts.values()
        )
        if need_pump:
            yield from self._motion_planner_.gen_plan_move(
                self._robot_position_, CocktailPosition.pump
            )
            self._robot_position_ = CocktailPosition.pump
            yield self._calculate_pump_task_(pump_amounts)
            logging.warning("no need pump (skipping)")

    def gen_plan_recipe_step(self, step: CocktailRecipeStep):
        match step.instruction:
            case CocktailRecipeShake(shake_duration_in_s=duration_in_s):
                yield from self.gen_plan_shake(shake_duration_in_s=duration_in_s)
            case CocktailRecipeAddIngredients():
                yield from self.gen_plan_add_ingredients(step.instruction.to_add)
            case _:
                raise Exception(f"unknown instruction {step.instruction}")

    def gen_empty_mixer(self):
        yield from self._motion_planner_.gen_plan_move(
            self._robot_position_, CocktailPosition.clean
        )
        self._robot_position_ = CocktailPosition.clean

        yield CocktailRobotCleanTask()

    def gen_clean_mixer(self):
        yield from self.gen_empty_mixer()

        yield from self._motion_planner_.gen_plan_move(
            self._robot_position_, CocktailPosition.pump
        )
        self._robot_position_ = CocktailPosition.pump

        yield CocktailRobotPumpTask(
            durations_in_s=[
                (
                    DefaultRecipeCocktailPlanner.CLEAN_PUMP_DURATION_IN_S
                    if i == DefaultRecipeCocktailPlanner.CLEAN_PUMP_SLOT
                    else 0.0
                )
                for i in range(4)  # TODO magic constant
            ]
        )

        yield from self.gen_empty_mixer()

    def gen_plan_pour_cocktail(self):
        assert self.runlock == False
        self.runlock = True

        yield from self.gen_clean_mixer()

        for step in self._recipe_.steps:
            yield from self.gen_plan_recipe_step(step)

        yield from self._motion_planner_.gen_plan_move(
            self._robot_position_, CocktailPosition.pour
        )
        self._robot_position_ = CocktailPosition.pour

        yield CocktailRobotPourTask()

        yield from self._motion_planner_.gen_plan_move(
            self._robot_position_, CocktailPosition.home
        )
        self._robot_position_ = CocktailPosition.home
