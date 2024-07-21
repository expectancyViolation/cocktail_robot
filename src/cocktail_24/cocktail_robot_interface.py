import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Generator, Type

from cocktail_24.pump_interface.pump_interface import PumpInterface
from cocktail_24.cocktail_robo import CocktailPosition, CocktailPlanner, CocktailRobotTask, CocktailRobotMoveTask, \
    CocktailRobotShakeTask, CocktailRobotZapfTask, CocktailRobotPumpTask, CocktailRobotPourTask
from cocktail_24.robot_interface.robocall_ringbuffer import RoboCallRingbuffer
from cocktail_24.robot_interface.robot_interface import RobotRelays, RoboTcpInterface, RobotOperations, \
    RoboTcpCommandResult


class CocktailRobotConfig:
    N_INPUT_BYTES = 20
    N_OUPUT_BYTES = 5
    input_relays = RobotRelays(address=22010, num_bytes=N_INPUT_BYTES)
    output_relays = RobotRelays(address=32010, num_bytes=N_OUPUT_BYTES)


@dataclass(frozen=True)
class CocktailRoboState:
    position: CocktailPosition
    cup_placed: bool
    cup_id: int
    ringbuffer_read_pos: int

    @staticmethod
    def parse_from_bytes(data: bytes) -> 'CocktailRoboState':
        assert len(data) == CocktailRobotConfig.N_OUPUT_BYTES
        position, ringbuffer_read_pos, *_ = data
        return CocktailRoboState(position=CocktailPosition(position), ringbuffer_read_pos=ringbuffer_read_pos,
                                 cup_placed=True, cup_id=1)


@dataclass(frozen=True)
class CocktailRobotSendEffect:
    data: str


@dataclass(frozen=True)
class CocktailRobotSendResponse:
    resp: str | None


@dataclass(frozen=True)
class CocktailRobotPullWorkEffect:
    pass


@dataclass(frozen=True)
class CocktailRobotReportWorkDoneEffect:
    task_id: uuid.UUID


@dataclass(frozen=True)
class CocktailRobotPullWorkResponse:
    task: CocktailRobotTask
    task_id: uuid.UUID


CocktailRobotEffect = CocktailRobotSendEffect | CocktailRobotPullWorkEffect | CocktailRobotReportWorkDoneEffect

CocktailRobotEffectResponse = CocktailRobotSendResponse | CocktailRobotPullWorkResponse


class CocktailTaskOpcodes(Enum):
    move_to = 1
    zapf = 2
    shake = 3
    pour = 4


class CocktailRobot:

    def __init__(self, tcp_interface: Type[RoboTcpInterface],
                 operations: RobotOperations) -> None:
        self._interface_ = tcp_interface
        self._ops_ = operations
        self._ringbuffer_: RoboCallRingbuffer | None = None
        self.robo_state: CocktailRoboState | None = None
        self._robo_tasks_: list[None | CocktailRobotPullWorkResponse] = [None] * RoboCallRingbuffer.RING_LEN

    def is_initialized(self) -> bool:
        return (self._ringbuffer_ is not None) and (self.robo_state is not None)

    @staticmethod
    def _wrap_tcp_effect_[T](gen: Generator[str | None, str | None, T]) -> Generator[
        CocktailRobotSendEffect, CocktailRobotEffectResponse, T]:
        x: str = next(gen)
        try:
            while True:
                resp = yield CocktailRobotSendEffect(data=x)
                assert isinstance(resp, CocktailRobotSendResponse)
                x = gen.send(resp.resp)
        except StopIteration as e:
            return e.value

    def _gen_get_state_(self) -> Generator[CocktailRobotSendEffect, CocktailRobotEffectResponse, CocktailRoboState]:
        resp = yield from CocktailRobot._wrap_tcp_effect_(
            self._interface_.gen_read_relays(CocktailRobotConfig.output_relays))
        return CocktailRoboState.parse_from_bytes(resp)

    def _gen_write_state_(self, readback: bool = False) -> Generator[
        CocktailRobotSendEffect, CocktailRobotEffectResponse, bool]:
        assert self.is_initialized()
        bytes_to_write = self._ringbuffer_.to_robo_bytes()
        assert len(bytes_to_write) <= CocktailRobotConfig.N_INPUT_BYTES
        padding = CocktailRobotConfig.N_INPUT_BYTES - len(bytes_to_write)
        bytes_to_write += bytes([0] * padding)

        resp = yield from CocktailRobot._wrap_tcp_effect_(
            self._interface_.gen_write_relays(CocktailRobotConfig.input_relays, bytes_to_write)
        )
        # print(f"got write resp {resp}")

        if readback:
            readback_resp = yield from CocktailRobot._wrap_tcp_effect_(
                self._interface_.gen_read_relays(CocktailRobotConfig.input_relays)
            )
            # print(f"got readback {readback_resp}")
            assert bytes_to_write == readback_resp
        return True

    def gen_sync_state(self, readback: bool = False) -> Generator[
        CocktailRobotSendEffect, CocktailRobotEffectResponse, bool]:
        self.robo_state = yield from self._gen_get_state_()
        write_ok = yield from self._gen_write_state_(readback=readback)
        return write_ok

    def gen_initialize(self):
        self.robo_state = yield from self._gen_get_state_()
        self._ringbuffer_ = RoboCallRingbuffer(initial_read_pos=self.robo_state.ringbuffer_read_pos)
        write_ok = yield from self._gen_write_state_()
        return write_ok

    def _gen_assure_running_(self):
        op_status = yield from CocktailRobot._wrap_tcp_effect_(self._interface_.gen_read_status())
        if op_status is not None:
            if not op_status.running:
                if op_status.safeguard:
                    # DANGER THIS STALLS THE LOOP!!
                    print("attempting restart")
                    could_start = yield from CocktailRobot._wrap_tcp_effect_(self._ops_.gen_start_job(None))
                    print(f"could restart {could_start}")
                else:
                    print("waiting on door")

    def gen_initialize_job(self):
        hold_status = yield from CocktailRobot._wrap_tcp_effect_(self._interface_.gen_hold_on(on=True))
        print(f"hold {hold_status}")
        op_status = yield from CocktailRobot._wrap_tcp_effect_(self._interface_.gen_read_status())
        print(f"{op_status=}")
        hold_status = yield from CocktailRobot._wrap_tcp_effect_(self._interface_.gen_hold_on(on=False))
        print(f"hold {hold_status}")
        op_status = yield from CocktailRobot._wrap_tcp_effect_(self._interface_.gen_read_status())
        # we need to reset the queue! there are race conditions!
        assert not op_status.running
        # reset job
        yield from self.gen_sync_state()
        could_reset = yield from CocktailRobot._wrap_tcp_effect_(self._interface_.gen_set_job("COCK", 0))
        print(f"could reset {could_reset}")
        assert could_reset == RoboTcpCommandResult.ok
        could_start = yield from CocktailRobot._wrap_tcp_effect_(self._ops_.gen_start_job("COCK"))
        print(f"could start {could_start}")
        yield from self.gen_sync_state()

    def gen_pour_cocktail(self):
        next_step_response = yield CocktailRobotPullWorkEffect()
        # print(next_step_response)
        # assert isinstance(next_step_response, CocktailRobotPullWorkResponse)

        print(f"received initial step {next_step_response}")
        while True:
            yield from self.gen_sync_state()

            # check liveness
            yield from self._gen_assure_running_()

            yield from self._gen_report_finished_tasks_()

            # handle work
            need_new_work = next_step_response is None
            if next_step_response is not None:
                need_new_work = self._enqueue_task_(next_step_response)
            if need_new_work:
                next_step_response = yield CocktailRobotPullWorkEffect()

    def _gen_report_finished_tasks_(self):
        # check robot feedback
        new_queue_pos = self.robo_state.ringbuffer_read_pos
        finished = []
        while (task_at_pos := self._robo_tasks_[new_queue_pos]) is not None:
            print(f"robot finished work:{task_at_pos}")
            finished.append(CocktailRobotReportWorkDoneEffect(task_at_pos.task_id))
            self._robo_tasks_[new_queue_pos] = None
            new_queue_pos = (new_queue_pos - 1) % RoboCallRingbuffer.RING_LEN
        for el in finished[::-1]:
            yield el

    @staticmethod
    def _encode_cocktail_task_(task: CocktailRobotTask) -> bytes:
        match task:
            case CocktailRobotMoveTask(to_pos=to_pos):
                return bytes([CocktailTaskOpcodes.move_to.value, to_pos.value, 0, 0])
            case CocktailRobotShakeTask(num_shakes=num_shakes):
                return bytes([CocktailTaskOpcodes.shake.value, num_shakes, 0, 0])
            case CocktailRobotZapfTask(slot=slot):
                return bytes([CocktailTaskOpcodes.zapf.value, slot, 0, 0])
            case CocktailRobotPourTask():
                return bytes([CocktailTaskOpcodes.pour.value, 0, 0, 0])
            case _:
                raise Exception(f"unknown task encoding {task=}")

    def _enqueue_task_(self, task: CocktailRobotPullWorkResponse) -> bool:
        assert self.is_initialized()
        encoded_task = CocktailRobot._encode_cocktail_task_(task.task)
        assert len(encoded_task) == RoboCallRingbuffer.ARG_CNT
        write_pos = self._ringbuffer_.write_pos
        could_feed = self._ringbuffer_.try_feed(encoded_task, self.robo_state.ringbuffer_read_pos)
        if could_feed:
            print(f"enqueued task {task}")
            self._robo_tasks_[write_pos] = task

        return could_feed
