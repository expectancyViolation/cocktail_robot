import logging
from asyncio import Protocol
from dataclasses import dataclass
from enum import Enum
from typing import Generator, Any


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
    def gen_write_relays(relays: RobotRelays, data: bytes) -> Generator[str, str, RoboTcpCommandResult]:
        ...

    @staticmethod
    def gen_read_relays(relays: RobotRelays) -> Generator[str, str, bytes]:
        ...

    @staticmethod
    def gen_servo_on() -> Generator[str, str, RoboTcpCommandResult]:
        ...

    @staticmethod
    def gen_hold_on(on: bool) -> Generator[str, str, RoboTcpCommandResult]:
        ...

    @staticmethod
    def gen_start_program(job_name: str) -> Generator[str, str, RoboTcpCommandResult]:
        ...

    @staticmethod
    def gen_set_job(job_name: str, line_number: int) -> Generator[str, str, RoboTcpCommandResult]:
        ...

    @staticmethod
    def gen_read_status() -> Generator[str, str, RoboStatus | None]:
        ...

    @staticmethod
    def gen_read_job_pos() -> Generator[str, str, str]:
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
    SET_JOB = "JSEQ"
    HOLD = "HOLD"

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
        args_to_yield = args if has_args else None
        resp = yield args_to_yield
        logging.info(f"done hostctrl {command} {resp}")
        return resp

    @staticmethod
    def _check_0000_(resp: str) -> RoboTcpCommandResult:
        return RoboTcpCommandResult.ok if (resp == '0000') else RoboTcpCommandResult.error

    @staticmethod
    def gen_write_relays(relays: RobotRelays, data: bytes) -> Generator[str, str, RoboTcpCommandResult]:
        assert len(data) == relays.num_bytes
        byte_string = ",".join(str(x) for x in data)
        arg_string = f"{relays.address},{8 * relays.num_bytes},{byte_string}"
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.WRITE_CMD, arg_string)
        return RoboTcpCommands._check_0000_(resp)

    @staticmethod
    def gen_read_relays(relays: RobotRelays) -> Generator[str, str, bytes]:
        arg_string = f"{relays.address}, {8 * relays.num_bytes}"
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.READ_CMD, arg_string)
        return bytes(int(x) for x in resp.split(","))

    @staticmethod
    def gen_servo_on() -> Generator[str, str, RoboTcpCommandResult]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.SVON_CMD, "1")
        return RoboTcpCommands._check_0000_(resp)

    @staticmethod
    def gen_hold_on(on: bool) -> Generator[str, str, RoboTcpCommandResult]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.HOLD, "1" if on else "0")
        return RoboTcpCommands._check_0000_(resp)

    @staticmethod
    def gen_start_program(job_name: str) -> Generator[str, str, RoboTcpCommandResult]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.START_CMD, job_name)
        return RoboTcpCommands._check_0000_(resp)

    # TODO: expensive (many roundtrips)
    @staticmethod
    def gen_read_status() -> Generator[str, str, RoboStatus | None]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.READ_STATUS)
        if resp is None:
            return None
        num_1, num_2 = (int(x) for x in resp.split(","))
        safety_resp = yield from RoboTcpCommands.gen_read_relays(RobotRelays(address=80020, num_bytes=1))
        safety = safety_resp[0] & (1 << 3)
        job_resp = yield from RoboTcpCommands.gen_read_job_pos()
        job_pos = RoboJobPos.from_resp(job_resp)
        success_count = yield from RoboTcpCommands.gen_read_var(RoboVarType.double, 42)
        if success_count is None:
            return None
        # print(f"{success_count=}")
        parsed_status = RoboStatus.from_nums(num_1, num_2, safety > 0, job_pos=job_pos,
                                             success_count=int(success_count))
        return parsed_status

    @staticmethod
    def gen_read_job_pos() -> Generator[str, str, str]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.READ_JOB_POS)
        return resp

    @staticmethod
    def gen_read_var(v: RoboVarType, index: int) -> Generator[str, str, Any]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.READ_VAR, f"{v.value},{index}")
        if isinstance(resp, str):
            if resp.startswith("Error"):
                return None
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

    @staticmethod
    def gen_set_job(job_name: str, line_number: int) -> Generator[str, str, RoboTcpCommandResult]:
        resp = yield from RoboTcpCommands._gen_hostctrl_(RoboTcpCommands.SET_JOB, f"{job_name},{line_number}")
        print(f"set job resp {resp}")
        return RoboTcpCommands._check_0000_(resp)


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
