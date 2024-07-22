from cocktail_24.robot_interface.robocall_ringbuffer import RoboCallRingbuffer


def test_robocall_ringbuffer():
    for initial_read_pos in range(0, RoboCallRingbuffer.RING_LEN):
        buffer = RoboCallRingbuffer(initial_read_pos=initial_read_pos)
        print(buffer)
        for i in range(2):
            assert buffer.try_feed(
                bytes([0x11 + i, 0x42 + i, 0x17, 0x9A + i]), initial_read_pos
            )
            print(buffer)
        buff_bytes = buffer.to_robo_bytes()
        assert not buffer.try_feed(bytes([1, 2, 3, 4]), initial_read_pos)
        assert buff_bytes == buffer.to_robo_bytes()
        assert buffer.try_feed(bytes([1, 2, 3, 4]), initial_read_pos + 2)
        assert buff_bytes != buffer.to_robo_bytes()
        buffer.clean(initial_read_pos + 3)
        print(buffer.to_robo_bytes())
        print(buffer)
        print((initial_read_pos + 3) % RoboCallRingbuffer.RING_LEN)
