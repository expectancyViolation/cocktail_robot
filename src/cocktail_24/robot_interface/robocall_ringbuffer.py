class RoboCallRingbuffer:
    RING_LEN = 4
    ARG_CNT = 4

    EMPTY = bytes([0] * ARG_CNT)

    def __init__(self, initial_read_pos: int = 0):
        self.write_pos = (initial_read_pos + 1) % RoboCallRingbuffer.RING_LEN
        self.buffer = [bytes([0] * RoboCallRingbuffer.ARG_CNT) for _ in range(RoboCallRingbuffer.RING_LEN)]

    def try_feed(self, args: bytes, read_pos: int) -> bool:
        read_pos %= RoboCallRingbuffer.RING_LEN
        assert self.write_pos != read_pos
        assert len(args) == RoboCallRingbuffer.ARG_CNT
        read_pos %= RoboCallRingbuffer.RING_LEN
        next_write_pos = (self.write_pos + 1) % RoboCallRingbuffer.RING_LEN
        full = read_pos == next_write_pos
        if full:
            return False
        print(f"fed into write pos {self.write_pos}")
        self.buffer[self.write_pos] = args
        self.write_pos = next_write_pos
        return True

    def is_empty(self, read_pos: int) -> bool:
        read_pos %= RoboCallRingbuffer.RING_LEN
        return self.write_pos == (read_pos + 1) % RoboCallRingbuffer.RING_LEN

    def clean(self, read_pos: int):
        read_pos %= 4
        assert self.write_pos != read_pos
        clean_pos = self.write_pos
        while clean_pos != read_pos:
            self.buffer[clean_pos] = bytes([0] * RoboCallRingbuffer.ARG_CNT)
            clean_pos = (clean_pos + 1) % RoboCallRingbuffer.RING_LEN
        # read pos was already read
        self.buffer[read_pos] = bytes([0] * RoboCallRingbuffer.ARG_CNT)

    def __str__(self):
        return f"RINGBUFF: {self.write_pos=} {[1 if self.buffer[i] != RoboCallRingbuffer.EMPTY else 0 for i in range(RoboCallRingbuffer.RING_LEN)]}"

    def to_robo_bytes(self) -> bytes:
        return bytes([self.write_pos] + [b for args in self.buffer for b in args])
