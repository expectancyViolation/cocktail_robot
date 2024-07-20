import socket
import time
from dataclasses import dataclass
from typing import Generator

import serial

from cocktail_24.cocktail_robot_interface import CocktailRobotSendEffect, CocktailRobotEffectResponse, \
    CocktailRobotSendResponse
from cocktail_24.cocktail_system import CocktailSystemEffect, GetTimeEffect, GetTimeResponse, PumpSendEffect, \
    PumpSendResponse


def cocktail_runtime[T](socket_: socket.socket, pump_serial: serial.Serial, cocktail_gen: Generator[
    CocktailSystemEffect, CocktailRobotEffectResponse, T]):
    try:
        to_handle = next(cocktail_gen)
        while True:
            match to_handle:
                case GetTimeEffect():
                    to_handle = cocktail_gen.send(GetTimeResponse(time=time.time()))
                case PumpSendEffect(to_send=to_send):
                    pump_serial.write(to_send)
                    to_handle = cocktail_gen.send(PumpSendResponse())
                case CocktailRobotSendEffect(data=to_send):
                    if to_send is not None:
                        # print(f"sending {to_send}")
                        socket_.send(f"{to_send}\r\n".encode("ascii"))
                    try:
                        response = socket_.recv(1024).decode("ascii").strip()
                        # print(f"received {response}")
                        to_handle = cocktail_gen.send(CocktailRobotSendResponse(resp=response))
                    except TimeoutError:
                        to_handle = cocktail_gen.send(CocktailRobotSendResponse(resp=None))
                case _:
                    raise Exception(f"wrong effect {to_handle}")
    except StopIteration as e:
        return e.value
