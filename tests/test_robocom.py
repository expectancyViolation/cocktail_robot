import logging
import random
import socket
import time
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Generator, Protocol, Any

import pytest


@dataclass(frozen=True)
class RobotRelays:
    address: int
    num_bytes: int


@dataclass(frozen=True)
class RobotReadCommand:
    relays: RobotRelays


@dataclass(frozen=True)
class RobotWriteCommand:
    relays: RobotRelays


class RoboTcpCommandResult(Enum):
    ok = "ok"
    error = "error"


@dataclass(frozen=True)
class RoboJobPos:
    job_name: str
    job_line: int
    job_step: int

    @staticmethod
    def from_resp(resp: str) -> 'RoboJobPos':
        n, l, s = resp.split(",")
        return RoboJobPos(n, int(l), int(s))


@dataclass(frozen=True)
class RoboStatus:
    remote: bool
    play: bool
    teach: bool
    safety_speed: bool
    running: bool
    is_auto: bool
    one_cycle: bool
    step: bool
    servo_on: bool
    error: bool
    alarm: bool
    hold_cmd: bool
    hold_ext: bool
    hold_pp: bool
    safeguard: bool
    job_pos: RoboJobPos | None
    success_count: int

    @staticmethod
    def from_nums(num_1: int, num_2: int, safeguard: bool, job_pos: RoboJobPos | None, success_count: int):
        bits_1 = [(num_1 & 1 << i) != 0 for i in range(7, -1, -1)]
        bits_2 = [(num_2 & 1 << i) != 0 for i in range(6, 0, -1)]
        return RoboStatus(*bits_1, *bits_2, safeguard=safeguard, job_pos=job_pos, success_count=success_count)


class RoboVarType(Enum):
    byte = 0
    integer = 1
    double = 2
    real = 3
    robot_axis_pos = 4
    base_axis_pos = 5
    station_axis_pos = 6


class RoboTcpInterface(Protocol):

    @staticmethod
    def gen_connect(keep_alive: int = -1) -> Generator[str, str, str]: ...

    @staticmethod
    def gen_write_relays(relays: RobotRelays, data: bytes) -> Generator[str, str, str | None]:
        ...

    @staticmethod
    def gen_read_relays(relays: RobotRelays) -> Generator[str, str, str]:
        ...

    @staticmethod
    def gen_servo_on() -> Generator[str, str, RoboTcpCommandResult]:
        ...

    @staticmethod
    def gen_start_program(job_name: str) -> Generator[str, str, RoboTcpCommandResult]:
        ...

    @staticmethod
    def gen_read_status() -> Generator[str, str, RoboStatus]:
        ...

    @staticmethod
    def gen_read_job_pos() -> Generator[str, str, RoboStatus]:
        ...

    @staticmethod
    def gen_read_var(v: RoboVarType, index: int) -> Generator[str, str, Any]:
        ...

    @staticmethod
    def gen_write_var(v: RoboVarType, index: int, val: Any) -> Generator[str, str, Any]:
        ...


class RoboTcpCommands(RoboTcpInterface):
    LINE_TERM = '\r\n'

    WRITE_CMD = "IOWRITE"
    READ_CMD = "IOREAD"
    SVON_CMD = "SVON"
    START_CMD = "START"
    READ_STATUS = "RSTATS"
    READ_JOB_POS = "RJSEQ"
    READ_VAR = "SAVEV"
    WRITE_VAR = "LOADV"

    @staticmethod
    def gen_connect(keep_alive: int = -1) -> Generator[str, str, str]:
        connect_string = 'CONNECT Robot_access'
        if keep_alive != 1:
            connect_string += ' Keep-Alive:{}'.format(keep_alive)
        resp = yield connect_string
        return resp

    @staticmethod
    def _gen_hostctrl_(command, args: str | None = None) -> Generator[str, str, str | None]:
        logging.info(f"hostctrl {command}")
        has_args = args is not None
        arg_len = (len(args) + len(RoboTcpCommands.LINE_TERM)) if has_args else 0
        resp = yield f"HOSTCTRL_REQUEST {command} {arg_len}"
        if not resp.startswith("OK"):
            return None
        resp = yield (args if has_args else None)
        logging.info(f"done hostctrl {command}")
        return resp

    @staticmethod
    def gen_write_relays(relays: RobotRelays, data: bytes) -> Generator[str, str, str | None]:
        assert len(data) == relays.num_bytes
        byte_string = ",".join(str(x) for x in data)
        arg_string = f"{relays.address},{8 * relays.num_bytes},{byte_string}"
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.WRITE_CMD, arg_string)
        return resp

    @staticmethod
    def gen_read_relays(relays: RobotRelays) -> Generator[str, str, str]:
        arg_string = f"{relays.address}, {8 * relays.num_bytes}"
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.READ_CMD, arg_string)
        return resp

    @staticmethod
    def gen_servo_on() -> Generator[str, str, RoboTcpCommandResult]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.SVON_CMD, "1")
        return RoboTcpCommandResult.ok if (resp == '0000') else RoboTcpCommandResult.error

    @staticmethod
    def gen_start_program(job_name: str) -> Generator[str, str, RoboTcpCommandResult]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.START_CMD, job_name)
        return RoboTcpCommandResult.ok if (resp == '0000') else RoboTcpCommandResult.error

    @staticmethod
    def gen_read_status() -> Generator[str, str, RoboStatus]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.READ_STATUS)
        num_1, num_2 = (int(x) for x in resp.split(","))
        # num_1, num_2 = 0, 0
        safety_resp = yield from RoboTcpCommands.gen_read_relays(RobotRelays(address=80020, num_bytes=1))
        safety = int(safety_resp) & (1 << 3)
        # job_resp = yield from RoboTcpCommands.gen_read_job_pos()
        # job_pos = RoboJobPos.from_resp(job_resp)
        success_count = yield from RoboTcpCommands.gen_read_var(RoboVarType.double, 42)
        # print(f"{success_count=}")
        parsed_status = RoboStatus.from_nums(num_1, num_2, safety > 0, job_pos=None,
                                             success_count=int(success_count))
        return parsed_status

    @staticmethod
    def gen_read_job_pos() -> Generator[str, str, RoboStatus]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.READ_JOB_POS)
        return resp

    @staticmethod
    def gen_read_var(v: RoboVarType, index: int) -> Generator[str, str, Any]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.READ_VAR, f"{v.value},{index}")
        return resp

    @staticmethod
    def gen_write_var(v: RoboVarType, index: int, val: Any, confirm: bool = True) -> Generator[str, str, Any]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.WRITE_VAR, f"{v.value},{index},{val}")
        if resp != '0000':
            return RoboTcpCommandResult.error
        if confirm:
            resp = yield from RoboTcpCommands.gen_read_var(v, index)
            logging.info(f"checking {resp=} equals {str(val)}")
            assert str(val) == resp

        return RoboTcpCommandResult.ok


# def test_can_format_commands():
#     input_relays = RobotRelays(address=22010, num_bytes=2)
#     output_relays = RobotRelays(address=32010, num_bytes=1)
#     write_cmd = RoboTcpCommands.write_relays(input_relays, bytes([1, 2]))
#     assert write_cmd == b"IOWRITE 22010,16,1,2\r\n"
#     read_cmd = RoboTcpCommands.read_relays(output_relays)
#     print(read_cmd)


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
class RobotOperationState(Enum):
    UNINITIALIZED = 0
    WORKING = 1
    WAITING_FOR_CMD = 2
    WAITING_FOR_CONFIRM = 3
    ERROR = 4


@dataclass(frozen=True)
class RobotRPCCommand:
    title: str
    cmd_id: int


class RobotOperations(Protocol):

    def gen_start_job(self, job_name: str) -> Generator[str, str, RoboTcpCommandResult]:
        ...

    def gen_run_job_once(self, job_name: str | None, wait_safety: bool = True) -> Generator[
        str, str, RoboTcpCommandResult]:
        ...

    def gen_run_job_until_completion(self, job_name: str) -> Generator[str, str, RoboTcpCommandResult]:
        ...


class DebaultRobotOperations(RobotOperations):

    def __init__(self, tcp_interface: RoboTcpInterface):
        self._interface_ = tcp_interface

    def gen_start_job(self, job_name: str, check_servo=True) -> Generator[str, str, RoboTcpCommandResult]:
        # status = yield from self._interface_.gen_read_status()
        # TODO: remove condition to avoid races?
        # print(f"servo status {status}")
        # if not status.servo_on:
            # _servo_on_ok = yield from self._interface_.gen_servo_on()
            # if not _servo_on_ok:
                # return RoboTcpCommandResult.error

        _servo_on_ok = yield from self._interface_.gen_servo_on()
        if not _servo_on_ok:
            return RoboTcpCommandResult.error
        start_ok = yield from self._interface_.gen_start_program(job_name=job_name)

        return start_ok

    def gen_run_job_once(self, job_name: str | None, wait_safety: bool = True) -> Generator[
        str, str, RoboTcpCommandResult]:
        status = yield from self._interface_.gen_read_status()
        if status.running:
            print("cannot start still running")
            return RoboTcpCommandResult.error
        # TODO, we only wait in the beginning,i.e. if safety is bouncy, we still fail
        if wait_safety:
            while not status.safeguard:
                # logging.info("waiting on safeguard")
                status = yield from self._interface_.gen_read_status()

        start_ok = yield from self.gen_start_job(job_name)
        if start_ok != RoboTcpCommandResult.ok:
            print("failed to start")
            return RoboTcpCommandResult.error
        while True:
            status = yield from self._interface_.gen_read_status()
            if not status.running:
                print(f"final status :{status=}")
                return RoboTcpCommandResult.ok

    def gen_run_job_until_completion(self, job_name: str) -> Generator[str, str, RoboTcpCommandResult]:
        initial_status = yield from self._interface_.gen_read_status()
        initial_success_count = initial_status.success_count
        res = yield from self.gen_run_job_once(job_name)
        while True:
            status = yield from self._interface_.gen_read_status()
            if initial_success_count != status.success_count:
                return RoboTcpCommandResult.ok
            print("job did not signal completion! rerunning...")
            res = yield from self.gen_run_job_once(None)


class CocktailPosition(Enum):
    home = 1
    zapf = 2
    shake = 3
    pour = 4
    clean = 5
    pump = 6


ALLOWED_COCKTAIL_MOVES = (
    (CocktailPosition.home, CocktailPosition.zapf),
    (CocktailPosition.home, CocktailPosition.shake),
    (CocktailPosition.home, CocktailPosition.clean),
    (CocktailPosition.home, CocktailPosition.pump),
    (CocktailPosition.shake, CocktailPosition.pour)
)


@dataclass(frozen=True)
class CocktailRoboState:
    position: CocktailPosition


class CocktailRobot:

    def __init__(self, tcp_interface: RoboTcpInterface, operations: RobotOperations) -> None:
        self._interface_ = tcp_interface
        self._ops_ = operations

    def gen_move_to(self, cock_pos: CocktailPosition):
        resp = yield from self._interface_.gen_write_var(RoboVarType.byte, 42, cock_pos.value)
        logging.info(f"set target pos {resp}")
        if resp == RoboTcpCommandResult.ok:
            resp = yield from self._ops_.gen_run_job_until_completion("COCK_MOV")
        return resp

    def gen_get_cocktail_robo_state(self):
        wbi_relay = RobotRelays(address=10160, num_bytes=1)
        resp = yield from self._interface_.gen_read_relays(wbi_relay)
        return CocktailRoboState(position=CocktailPosition(int(resp)))


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
    input_relays = RobotRelays(address=22010, num_bytes=2)
    output_relays = RobotRelays(address=32010, num_bytes=1)

    commands = RoboTcpCommands
    robo_socket.settimeout(5)
    run_command_gen_sync(robo_socket, commands.gen_connect())
    run_command_gen_sync(robo_socket, commands.gen_read_status())
    ops = DebaultRobotOperations(commands)
    cocktail = CocktailRobot(tcp_interface=commands, operations=ops)

    cocktail_nbs: defaultdict[CocktailPosition, set[CocktailPosition]] = defaultdict(lambda: set())
    for x, y in ALLOWED_COCKTAIL_MOVES:
        cocktail_nbs[x].add(y)
        cocktail_nbs[y].add(x)

    for i in range(10):
        print(f"test_move {i}:")
        state = run_command_gen_sync(robo_socket, cocktail.gen_get_cocktail_robo_state())
        target_pos = random.choice([*cocktail_nbs[state.position]])
        print(f"move from {state.position=} {target_pos=}")
        state = run_command_gen_sync(robo_socket, cocktail.gen_move_to(target_pos))

    # for i in range(5):
    #     run_command_gen_sync(robo_socket, ops.gen_run_job("BOP"))
    # run_command_gen_sync(robo_socket, ops.gen_run_job("COCK"))

    # for i in range(9):
    #     run_command_gen_sync(robo_socket, commands.gen_write_var(RoboVarType.byte, 42, i))
    #     time.sleep(1)
    # run_command_gen_sync(robo_socket, ops.gen_run_job_until_completion("COCK"))

    # time.sleep(2)

    # print(run_command_gen_sync(robo_socket, RoboTcpCommands.gen_start_program("COCK")))

    # for b1 in range(240):
    #     G_write = RoboTcpCommands.gen_write_relays(input_relays, bytes([b1, 2]))
    #     print(run_command_gen_sync(G_write, robo_socket))
    #     time.sleep(1)
    # G_read = RoboTcpCommands.gen_read_relays(output_relays)
    # print(run_command_gen_sync(G_read, robo_socket))
