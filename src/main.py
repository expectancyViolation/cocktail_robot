import asyncio
import datetime
import logging
import uuid

from cocktail_24.cocktail.cocktail_api import (
    InMemoryCocktailBarStatePersistence,
    CocktailBarStatePersistence,
)
from cocktail_24.cocktail.cocktail_bookkeeping import (
    CocktailBarState,
    SlotStatus,
    SlotPath,
    OrderPlacedEvent,
    UserId,
)
from cocktail_24.cocktail.cocktail_recipes import RecipeId
from cocktail_24.cocktail_management import CocktailManagement
from cocktail_24.cocktail_robot_interface import CocktailRobot
from cocktail_24.cocktail_runtime import (
    async_cocktail_runtime,
)
from cocktail_24.cocktail_system import (
    CocktailSystem,
    CocktailSystemPlan,
)
from cocktail_24.planning.cocktail_planner import (
    CocktailSystemConfig,
    CocktailPumpStationConfig,
    SimpleRobotMotionPlanner,
    SimpleRobotIngredientPlanner,
    SimpleRobotIngredientPlannerConfig,
    CocktailZapfStationConfig,
)
from cocktail_24.planning.cocktail_planning import (
    DefaultStaticCocktailPlanning,
    DefaultRecipeCocktailPlannerFactory,
)
from cocktail_24.pump_interface.pump_interface import (
    DefaultPumpSerialEncoder,
    PumpInterface,
)
from cocktail_24.recipe_samples import TypicalIngredients, SampleRecipes
from cocktail_24.robot_interface.robot_interface import RoboTcpCommands
from cocktail_24.robot_interface.robot_operations import DefaultRobotOperations


def configure_system() -> tuple[CocktailSystem, CocktailSystemConfig]:
    commands = RoboTcpCommands

    ops = DefaultRobotOperations(commands)

    cocktail = CocktailRobot(tcp_interface=commands, operations=ops)

    system_config = CocktailSystemConfig(
        zapf_config=CocktailZapfStationConfig(ml_per_zapf=30.0, zapf_station_id="zapf"),
        pump_config=CocktailPumpStationConfig(
            ml_per_second=16.0, pump_station_id="pump"
        ),
        single_shake_duration_in_s=2.0,
    )

    pump_serial_encoder = DefaultPumpSerialEncoder()
    pump = PumpInterface(encoder=pump_serial_encoder)

    cocktail_system = CocktailSystem(robot=cocktail, pump=pump)

    return cocktail_system, system_config


def configure_planning(system_config: CocktailSystemConfig):
    motion_planner = SimpleRobotMotionPlanner()
    ingredient_planner = SimpleRobotIngredientPlanner(
        config=SimpleRobotIngredientPlannerConfig(system_config=system_config)
    )

    planner_factory = DefaultRecipeCocktailPlannerFactory(
        ingredient_planner=ingredient_planner,
        motion_planner=motion_planner,
        system_config=system_config,
    )

    return DefaultStaticCocktailPlanning(planner_factory=planner_factory)


def configure_management(
    cocktail_system: CocktailSystem,
    system_config: CocktailSystemConfig,
    persistence: CocktailBarStatePersistence,
):
    # persistence = InMemoryCocktailBarStatePersistence()
    management = CocktailManagement(
        cocktail_persistence=persistence,
        cocktail_system=cocktail_system,
        system_config=system_config,
        planning=configure_planning(system_config=system_config),
    )
    return management


def configure_initial_state():
    slots_status = [
        SlotStatus(
            slot_path=SlotPath(station_id="zapf", slot_id=9),
            available_amount_in_ml=300.0,
            ingredient_id=TypicalIngredients.whiskey,
        ),
        SlotStatus(
            slot_path=SlotPath(station_id="zapf", slot_id=1),
            available_amount_in_ml=300.0,
            ingredient_id=TypicalIngredients.tequila,
        ),
        SlotStatus(
            slot_path=SlotPath(station_id="zapf", slot_id=5),
            available_amount_in_ml=300.0,
            ingredient_id=TypicalIngredients.gin,
        ),
        SlotStatus(
            slot_path=SlotPath(station_id="zapf", slot_id=7),
            available_amount_in_ml=700.0,
            ingredient_id=TypicalIngredients.vodka,
        ),
        SlotStatus(
            slot_path=SlotPath(station_id="pump", slot_id=0),
            available_amount_in_ml=10000.0,
            ingredient_id=TypicalIngredients.vodka,
        ),
    ]
    the_vomit = SampleRecipes.the_vomit()
    good_order_id = uuid.uuid4()
    mth_id = uuid.uuid4()
    inital_state = CocktailBarState(
        slots=slots_status,
        recipes={the_vomit.recipe_id: the_vomit},
        orders={},
        order_queue=tuple(),
    )
    events = [
        OrderPlacedEvent(
            order_id=good_order_id,
            recipe_id=the_vomit.recipe_id,
            user_id=UserId(mth_id),
        ),
    ]

    timed_events = [(datetime.datetime.now(), event) for event in events]
    return CocktailBarState.apply_events(
        events=timed_events, initial_state=inital_state
    )


class FakeSerial:

    def write(self, data):
        pass


def run():
    system, system_config = configure_system()
    management = configure_management(system, system_config)
    asyncio.run(async_cocktail_runtime(cocktail_gen=gen_run_robo(system, management)))


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s",
        level=logging.WARNING,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    run()
