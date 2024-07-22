import asyncio
import logging
import uuid

from cocktail_24.cocktail.cocktail_api import InMemoryCocktailBarStatePersistence
from cocktail_24.cocktail.cocktail_bookkeeping import CocktailZapfStationConfig
from cocktail_24.cocktail_management import CocktailManagement
from cocktail_24.planning.cocktail_planning import DefaultRecipeCocktailPlannerFactory
from cocktail_24.cocktail_robot_interface import CocktailRobot
from cocktail_24.cocktail_runtime import (
    async_cocktail_runtime,
)
from cocktail_24.cocktail_system import (
    CocktailSystem,
    CocktailSystemPlan,
)
from cocktail_24.pump_interface.pump_interface import (
    DefaultPumpSerialEncoder,
    PumpInterface,
)
from cocktail_24.recipe_samples import TypicalIngredients, SampleRecipes
from cocktail_24.robot_interface.robot_interface import RoboTcpCommands
from cocktail_24.robot_interface.robot_operations import DefaultRobotOperations


def configure_system() -> tuple[CocktailSystem, CocktailSystemPlan]:
    commands = RoboTcpCommands

    ops = DefaultRobotOperations(commands)

    cocktail = CocktailRobot(tcp_interface=commands, operations=ops)

    zapf_config = CocktailZapfStationConfig(
        ml_per_zapf=20,
        zapf_slots={
            0: TypicalIngredients.gin,
            4: TypicalIngredients.vodka,
            7: TypicalIngredients.tequila,
            11: TypicalIngredients.whiskey,
        },
        # cup_limit_in_ml=250
    )

    planner_factory = DefaultRecipeCocktailPlannerFactory(zapf_config=zapf_config)

    pump_serial_encoder = DefaultPumpSerialEncoder()
    pump = PumpInterface(encoder=pump_serial_encoder)

    cocktail_system = CocktailSystem(robot=cocktail, pump=pump)

    plan_steps = [
        *planner_factory.get_planner(SampleRecipes.the_vomit()).gen_plan_pour_cocktail()
    ]
    plan = CocktailSystemPlan(steps=(*plan_steps,), plan_uuid=uuid.uuid4())

    return cocktail_system, plan


def configure_management(cocktail_system: CocktailSystem):
    persistence = InMemoryCocktailBarStatePersistence()
    management = CocktailManagement(
        cocktail_persistence=persistence, cocktail_system=cocktail_system
    )


def gen_run_robo(cocktail_system: CocktailSystem, initial_plan=None):

    # TODO: system factory to allow reset?
    yield from cocktail_system.gen_initialize()

    if initial_plan is not None:
        cocktail_system.run_plan(initial_plan)

    execution = cocktail_system.gen_run()
    effect = next(execution)
    while True:
        send = yield effect
        effect = execution.send(send)


class FakeSerial:

    def write(self, data):
        pass


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s",
        level=logging.WARNING,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    system, plan = configure_system()
    asyncio.run(async_cocktail_runtime(cocktail_gen=gen_run_robo(system, plan)))
