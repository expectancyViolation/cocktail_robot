from enum import Enum
from typing import Generator, Protocol

from cocktail_24.cocktail_robo import CocktailRobotPumpTask


class PumpStatus(Enum):
    ready = 1
    pumping = 2
    finished = 4
    interrupted = 5


class PumpSetup:
    NUM_PUMPS = 4


class PumpSerialEncoder(Protocol):

    def encode_slots(self, slots_on: list[bool]) -> bytes:
        ...


class DefaultPumpSerialEncoder(PumpSerialEncoder):

    def __init__(self):
        self.watchdog_bit = 0

    def encode_slots(self, slots_on: list[bool]) -> bytes:
        assert len(slots_on) == PumpSetup.NUM_PUMPS
        res = self.watchdog_bit
        for slot in slots_on[::-1]:
            res = 2 * res + (1 if slot else 0)
        return bytes([res])


class PumpInterface:

    def __init__(self, encoder: PumpSerialEncoder):
        self.pump_durations = [-1.0] * PumpSetup.NUM_PUMPS
        self.status: PumpStatus = PumpStatus.ready
        self._encoder_ = encoder
        self.previous_time = .0

    def _update_durations_(self, current_time: float):
        dt = max(0.0, current_time - self.previous_time)
        for i in range(PumpSetup.NUM_PUMPS):
            self.pump_durations[i] -= dt

    def _get_pumping_slots_(self) -> list[bool]:
        return [x > 0.0 for x in self.pump_durations]

    def _check_pump_done_(self) -> bool:
        return not any(self._get_pumping_slots_())

    def update(self, current_time: float, robot_at_pump_spot: bool):
        match self.status:
            case PumpStatus.pumping:
                self._update_durations_(current_time)
                if not robot_at_pump_spot:
                    self.status = PumpStatus.interrupted
                if self._check_pump_done_():
                    self.status = PumpStatus.finished

    def reset(self):
        self.status = PumpStatus.ready
        self.pump_durations = [-1.0] * PumpSetup.NUM_PUMPS

    def request_pump(self, pump_task: CocktailRobotPumpTask) -> bool:
        if self.status != PumpStatus.ready:
            return False
        for slot, duration in pump_task.durations_in_s.items():
            self.pump_durations[slot] = duration
        self.status = PumpStatus.pumping

    def get_pump_msg(self) -> bytes:
        return self._encoder_.encode_slots(self._get_pumping_slots_())
