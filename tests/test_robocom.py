import socket

import pytest

from src.cocktail_24.cocktail_robot_interface import CocktailRobot
from src.cocktail_24.cocktail_runtime import cocktail_runtime
from src.cocktail_24.robot_interface.robot_interface import RoboTcpCommands
from src.cocktail_24.robot_interface.robot_operations import DefaultRobotOperations
from tests.test_cocktail_planning import get_the_vomit_planner


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


def test_can_read_data(robo_socket: socket.socket):
    commands = RoboTcpCommands
    robo_socket.settimeout(5)
    run_command_gen_sync(robo_socket, commands.gen_connect())
    status = run_command_gen_sync(robo_socket, commands.gen_read_status())
    print(status)
    ops = DefaultRobotOperations(commands)

    # run_command_gen_sync(robo_socket, commands.gen_set_job("COCK", 10))

    cocktail = CocktailRobot(tcp_interface=commands, operations=ops)

    planner = get_the_vomit_planner()

    cocktail_runtime(robo_socket, cocktail.gen_initialize())
    cocktail_runtime(robo_socket, cocktail.gen_pour_cocktail(planner))
