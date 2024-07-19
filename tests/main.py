import logging
import socket

from tests.test_robocom import test_can_read_data

if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        connection.connect(("192.168.255.1", 80))

        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)
        test_can_read_data(connection)
    finally:
        connection.close()
