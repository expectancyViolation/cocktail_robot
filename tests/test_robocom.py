import socket

import pytest


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


