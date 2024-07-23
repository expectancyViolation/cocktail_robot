import asyncio
import logging
import socket
import time
from typing import Generator, Any

import serial

from cocktail_24.cocktail_system import (
    CocktailSystemEffect,
    GetTimeEffect,
    GetTimeResponse,
    PumpSendEffect,
    PumpSendResponse,
    CocktailRobotSendResponse,
    CocktailRobotSendEffect,
)


def run_command_gen_sync(robo_socket, gen):
    try:
        to_send = next(gen)
        while True:
            # print(f"{to_send=}")
            if to_send is not None:
                robo_socket.send(f"{to_send}\r\n".encode("ascii"))
            response = robo_socket.recv(1024).decode("ascii").strip()
            # print(f"got response {response=}")
            to_send = gen.send(response)
    except StopIteration as e:
        return e.value


def cocktail_runtime[
    T
](
    socket_: socket.socket,
    pump_serial: serial.Serial,
    cocktail_gen: Generator[CocktailSystemEffect, Any, T],
):
    try:
        to_handle = next(cocktail_gen)
        while True:
            match to_handle:
                case GetTimeEffect():
                    to_handle = cocktail_gen.send(GetTimeResponse(time=time.time()))
                case PumpSendEffect(to_send=to_send):
                    pump_serial.write(to_send)
                    to_handle = cocktail_gen.send(PumpSendResponse())
                case CocktailRobotSendEffect(to_send=to_send):
                    if to_send is not None:
                        # print(f"sending {to_send}")
                        socket_.send(f"{to_send}\r\n".encode("ascii"))
                    try:
                        response = socket_.recv(1024).decode("ascii").strip()
                        # print(f"received {response}")
                        to_handle = cocktail_gen.send(
                            CocktailRobotSendResponse(resp=response)
                        )
                    except TimeoutError:
                        to_handle = cocktail_gen.send(
                            CocktailRobotSendResponse(resp=None)
                        )
                case _:
                    raise Exception(f"wrong effect {to_handle}")
    except StopIteration as e:
        return e.value


from serial_asyncio import open_serial_connection


async def async_cocktail_runtime(cocktail_gen):
    real_pump = True
    real_robo = True
    if real_robo:
        robo_reader, robo_writer = await asyncio.open_connection("192.168.255.1", 80)
    if real_pump:
        reader, writer = await open_serial_connection(
            url="/dev/ttyUSB0", baudrate=115200
        )
    try:
        # print("FEED")
        to_handle = next(cocktail_gen)
        while True:
            logging.debug(f"runtime to handle {to_handle}")
            match to_handle:
                case GetTimeEffect():
                    to_handle = cocktail_gen.send(GetTimeResponse(time=time.time()))
                case PumpSendEffect(to_send=to_send):
                    writer.write(to_send)
                    to_handle = cocktail_gen.send(PumpSendResponse())
                case CocktailRobotSendEffect(to_send=to_send):
                    if to_send is not None:
                        logging.debug(f"sending {to_send}")
                        robo_writer.write(f"{to_send}\r\n".encode("ascii"))
                    try:
                        raw_resp = await robo_reader.readuntil(b"\r")
                        response = raw_resp.decode("ascii").strip()
                        logging.debug(f"received {response}")
                        to_handle = cocktail_gen.send(
                            CocktailRobotSendResponse(resp=response)
                        )
                    except TimeoutError:
                        # TODO DANGER: is this useful at all?
                        to_handle = cocktail_gen.send(
                            CocktailRobotSendResponse(resp=None)
                        )
                case _:
                    raise Exception(f"wrong effect {to_handle}")
    except StopIteration as e:
        return e.value
