import socket

import pytest

from cocktail_24.cocktail_planning import DefaultRecipeCocktailPlannerFactory
from cocktail_24.cocktail_robo import CocktailZapfConfig
from cocktail_24.cocktail_system import CocktailSystem
from cocktail_24.pump_interface.pump_interface import PumpInterface, DefaultPumpSerialEncoder
from cocktail_24.recipe_samples import TypicalIngredients, SampleRecipes
from cocktail_24.cocktail_robot_interface import CocktailRobot
from cocktail_24.cocktail_runtime import cocktail_runtime
from cocktail_24.robot_interface.robot_interface import RoboTcpCommands
from cocktail_24.robot_interface.robot_operations import DefaultRobotOperations


@pytest.fixture
def robo_socket():
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        connection.connect(("192.168.255.1", 80))
        yield connection
    finally:
        connection.close()


# assumptions:
#   we have a perfect model of the robot operations:
#       - robot does not change state on its own
#       - only exception: robot error/reset
#       - on error/reset we have to resync whole state
#           - robot position
#           - robot bottle content


def run_command_gen_sync(socket, G):
    try:
        to_send = next(G)
        while True:
            # print(f"{to_send=}")
            if to_send is not None:
                socket.send(f"{to_send}\r\n".encode("ascii"))
            response = socket.recv(1024).decode("ascii").strip()
            # print(f"got response {response=}")
            to_send = G.send(response)
    except StopIteration as e:
        return e.value


