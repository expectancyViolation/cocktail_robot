from dataclasses import dataclass
from enum import Enum
from typing import Generator, Type

from cocktail_24.pump_interface.pump_interface import PumpInterface
from src.cocktail_24.cocktail_robo import CocktailPosition, CocktailPlanner, CocktailRobotTask, CocktailRobotMoveTask, \
    CocktailRobotShakeTask, CocktailRobotZapfTask, CocktailRobotPumpTask
from src.cocktail_24.robot_interface.robocall_ringbuffer import RoboCallRingbuffer
from src.cocktail_24.robot_interface.robot_interface import RobotRelays, RoboTcpInterface, RobotOperations, \
    RoboTcpCommandResult


class CocktailRobotConfig:
    N_INPUT_BYTES = 20
    N_OUPUT_BYTES = 5
    input_relays = RobotRelays(address=22010, num_bytes=N_INPUT_BYTES)
    output_relays = RobotRelays(address=32010, num_bytes=N_OUPUT_BYTES)


@dataclass(frozen=True)
class CocktailRoboState:
    position: CocktailPosition
    ringbuffer_read_pos: int

    @staticmethod
    def parse_from_bytes(data: bytes) -> 'CocktailRoboState':
        assert len(data) == CocktailRobotConfig.N_OUPUT_BYTES
        position, ringbuffer_read_pos, *_ = data
        return CocktailRoboState(position=CocktailPosition(position), ringbuffer_read_pos=ringbuffer_read_pos)


@dataclass(frozen=True)
class CocktailRobotSendEffect:
    data: str



@dataclass(frozen=True)
class CocktailRobotSendResponse:
    resp: str | None


CocktailRobotEffect = CocktailRobotSendEffect

CocktailRobotEffectResponse = CocktailRobotSendResponse


class CocktailTaskOpcodes(Enum):
    move_to = 1
    zapf = 2
    shake = 3


class CocktailRobot:

    def __init__(self, tcp_interface: Type[RoboTcpInterface],
                 operations: RobotOperations) -> None:
        self._interface_ = tcp_interface
        self._ops_ = operations
        self._ringbuffer_: RoboCallRingbuffer | None = None
        self._robo_state_: CocktailRoboState | None = None
        self._robo_tasks_ = [None] * RoboCallRingbuffer.RING_LEN

    def is_initialized(self) -> bool:
        return (self._ringbuffer_ is not None) and (self._robo_state_ is not None)

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
        self._robo_state_ = yield from self._gen_get_state_()
        write_ok = yield from self._gen_write_state_(readback=readback)
        return write_ok

    def gen_initialize(self):
        self._robo_state_ = yield from self._gen_get_state_()
        self._ringbuffer_ = RoboCallRingbuffer(initial_read_pos=self._robo_state_.ringbuffer_read_pos)
        write_ok = yield from self._gen_write_state_()
        return write_ok

    def gen_pour_cocktail(self, planner: CocktailPlanner):
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
        pour = planner.gen_plan_pour_cocktail()
        yield from self.gen_sync_state()
        next_step = next(pour)
        assert next_step is not None
        print(f"received initial step {next_step}")
        queue_pos = self._robo_state_.ringbuffer_read_pos
        while True:
            yield from self.gen_sync_state()

            # check liveness
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

            # check robot feedback
            new_queue_pos = self._robo_state_.ringbuffer_read_pos
            if new_queue_pos != queue_pos:
                print(f"robot finished work:{self._robo_tasks_[new_queue_pos]}")
                queue_pos = new_queue_pos
                print(self._robo_state_)

            # handle work
            handled = False
            match next_step:
                case CocktailRobotMoveTask():
                    handled = self._enqueue_task_(next_step)
                case CocktailRobotZapfTask():
                    handled = self._enqueue_task_(next_step)
                case CocktailRobotShakeTask():
                    handled = self._enqueue_task_(next_step)
                case CocktailRobotPumpTask():
                    # everything freezes until we are dome pumping
                    handled = yield CocktailRobotPumpEffect(pump_task=next_step)

                    # fetch next work item
            if handled:
                try:
                    next_step = pour.send(None)
                    print(f"received next step{next_step}")
                except StopIteration as e:
                    print("done stepping")
                    # sync last op
                    yield from self.gen_sync_state()
                    return

    @staticmethod
    def _encode_cocktail_task_(task: CocktailRobotTask) -> bytes:
        match task:
            case CocktailRobotMoveTask(to_pos=to_pos):
                return bytes([CocktailTaskOpcodes.move_to.value, to_pos.value, 0, 0])
            case CocktailRobotShakeTask(num_shakes=num_shakes):
                return bytes([CocktailTaskOpcodes.shake.value, num_shakes, 0, 0])
            case CocktailRobotZapfTask(slot=slot):
                return bytes([CocktailTaskOpcodes.zapf.value, slot, 0, 0])
            case _:
                raise Exception(f"unknown task encoding {task=}")

    def _enqueue_task_(self, task: CocktailRobotTask) -> bool:
        assert self.is_initialized()
        encoded_task = CocktailRobot._encode_cocktail_task_(task)
        assert len(encoded_task) == RoboCallRingbuffer.ARG_CNT
        write_pos = self._ringbuffer_.write_pos
        could_feed = self._ringbuffer_.try_feed(encoded_task, self._robo_state_.ringbuffer_read_pos)
        if could_feed:
            self._robo_tasks_[write_pos] = task

        return could_feed
