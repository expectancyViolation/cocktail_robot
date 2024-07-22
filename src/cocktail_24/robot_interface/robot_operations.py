from typing import Generator, Type

from cocktail_24.robot_interface.robot_interface import (
    RobotOperations,
    RoboTcpInterface,
    RoboTcpCommandResult,
)


class DefaultRobotOperations(RobotOperations):

    def __init__(self, tcp_interface: Type[RoboTcpInterface]):
        self._interface_ = tcp_interface

    def gen_start_job(
        self, job_name: str, check_servo=True
    ) -> Generator[str, str, RoboTcpCommandResult]:
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

    def gen_run_job_once(
        self, job_name: str | None, wait_safety: bool = True
    ) -> Generator[str, str, RoboTcpCommandResult]:
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

    def gen_run_job_until_completion(
        self, job_name: str
    ) -> Generator[str, str, RoboTcpCommandResult]:
        initial_status = yield from self._interface_.gen_read_status()
        initial_success_count = initial_status.success_count
        res = yield from self.gen_run_job_once(job_name)
        while True:
            status = yield from self._interface_.gen_read_status()
            if initial_success_count != status.success_count:
                return RoboTcpCommandResult.ok
            print("job did not signal completion! rerunning...")
            res = yield from self.gen_run_job_once(None)
