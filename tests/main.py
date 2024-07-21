import logging
import socket

import serial

from cocktail_24.cocktail_planning import DefaultRecipeCocktailPlannerFactory
from cocktail_24.cocktail_robo import CocktailZapfConfig
from cocktail_24.cocktail_robot_interface import CocktailRobot
from cocktail_24.cocktail_runtime import cocktail_runtime
from cocktail_24.cocktail_system import CocktailSystem
from cocktail_24.pump_interface.pump_interface import DefaultPumpSerialEncoder, PumpInterface
from cocktail_24.recipe_samples import TypicalIngredients, SampleRecipes
from cocktail_24.robot_interface.robot_interface import RoboTcpCommands
from cocktail_24.robot_interface.robot_operations import DefaultRobotOperations
from tests.test_robocom import run_command_gen_sync


def main(robo_socket: socket.socket, pump_serial: serial.Serial):
    commands = RoboTcpCommands
    robo_socket.settimeout(5)
    run_command_gen_sync(robo_socket, commands.gen_connect())
    status = run_command_gen_sync(robo_socket, commands.gen_read_status())
    print(status)
    ops = DefaultRobotOperations(commands)

    # run_command_gen_sync(robo_socket, commands.gen_set_job("COCK", 10))

    cocktail = CocktailRobot(tcp_interface=commands, operations=ops)

    zapf_config = CocktailZapfConfig(
        ml_per_zapf=20,
        zapf_slots={0: TypicalIngredients.gin, 4: TypicalIngredients.vodka, 7: TypicalIngredients.tequila,
                    11: TypicalIngredients.whiskey},
        cup_limit_in_ml=250
    )

    planner_factory = DefaultRecipeCocktailPlannerFactory(zapf_config=zapf_config)

    pump_serial_encoder = DefaultPumpSerialEncoder()
    pump = PumpInterface(encoder=pump_serial_encoder)

    cocktail_system = CocktailSystem(robot=cocktail, planner_factory=planner_factory, pump=pump)

    cocktail_runtime(socket_=robo_socket, pump_serial=pump_serial, cocktail_gen=cocktail.gen_initialize())

    cocktail_runtime(socket_=robo_socket, pump_serial=pump_serial, cocktail_gen=cocktail.gen_initialize_job())

    cocktail_runtime(socket_=robo_socket, pump_serial=pump_serial,
                     cocktail_gen=cocktail_system.gen_handle_cocktail_recipe(SampleRecipes.the_vomit()))

    # cocktail_runtime(robo_socket, cocktail.gen_initialize())
    # cocktail_runtime(robo_socket, cocktail.gen_pour_cocktail(planner))


class FakeSerial:

    def write(self, data):
        pass


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
        level=logging.WARNING,
        datefmt='%Y-%m-%d %H:%M:%S')
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        connection.connect(("192.168.255.1", 80))

        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)
        # with serial.Serial("/dev/ttyUSB0", 115200, timeout=1) as ser:
        ser = FakeSerial()
        main(connection, ser)
    finally:
        connection.close()
