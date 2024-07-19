import socket
import time
import asyncio

# TCP_IP= '127.0.0.1'
TCP_IP = '192.168.255.1'
TCP_PORT = 80
BUFFER_SIZE = 1024
IN_RELAYS = [22010, 16]
RESP_RELAYS = [32010, 8]
TEST_RECIPE = [1, 5, 11]
SHAKE_COUNT = 2


# pulsePos=[791,-70687,-109335,-4061,-10306,-9046]
# pulsePosString=str(pulsePos)
# pulsePosString=pulsePosString[1:-1]

# TODO ENUM
# 0=UNSET
# 1=MAKE_READY
# 2=MIX
# 3=HANDOVER

class TcpConnection():
    def __init__(self, loop):
        self.loop = loop

    async def __aenter__(self):
        reader, writer = await asyncio.open_connection(TCP_IP, TCP_PORT)
        self.reader = reader
        self.writer = writer
        return self

    async def __aexit__(self):
        self.writer.close()

    async def send_command(self, cmd, args):
        try:
            byteString = args.encode()
            arglen = len(byteString)
            # print(arglen)
            cmd = 'HOSTCTRL_REQUEST ' + cmd
            cmd += str(arglen)
            cmd += '\r\n'
            # print(cmd)
            print(cmd)
            self.writer.write(cmd.encode())
            data = await self.reader.read(BUFFER_SIZE)
            print("DATA")
            print(data)
            print("\n")
            if arglen:
                print(byteString)
                self.writer.write(byteString)
            data = await self.reader.read(BUFFER_SIZE)
            print(data)
            return data
        except Exception as e:
            print("command failed:{}".format(cmd))
            print(str(e))

    async def getState(self):
        relayString = "{}, {}\r".format(RESP_RELAYS[0], RESP_RELAYS[1])
        newState = await self.send_command("IOREAD ", relayString)
        self.state = newState

    async def initiateConnection(self, keep_alive=-1):
        try:
            connect_string = 'CONNECT Robot_access'
            if keep_alive != 1:
                connect_string += ' Keep-Alive:{}'.format(keep_alive)
            connect_string += '\r\n'
            print(connect_string)
            self.writer.write(connect_string.encode('ASCII'))
            data = await self.reader.read(BUFFER_SIZE)
            print(data)
            await self.send_command("IOWRITE ", "{0},{1},{2},{3}\r".format(IN_RELAYS[0], IN_RELAYS[1], 0, 0))
            await self.getState()
            try:
                print("read state:{}".format(self.state))

                if int(self.state) == 0:
                    await self.send_command("IOWRITE ", "{0},{1},{2},{3}\r".format(IN_RELAYS[0], IN_RELAYS[1], 254, 0))
            except:
                print("???")
        except Exception as e:
            print("rofl")
            print(e)

    async def waitForState(self, stateID):
        while 1:
            await self.getState()
            # print(self.state);
            await asyncio.sleep(.3)
            try:
                recStateID = int(self.state)
                # print("read state")
                if recStateID == stateID:
                    return stateID
            except:
                print("failed to read state")
                print(self.state)
                await asyncio.sleep(2)

    async def sendNextTransition(self, transID, p1):
        await self.waitForState(1)
        print("ready for transition arg")
        await self.send_command("IOWRITE ", "{0},{1},{2},{3}\r".format(IN_RELAYS[0], IN_RELAYS[1], transID, p1))
        await self.waitForState(0)
        print("received 'reset'")
        await self.send_command("IOWRITE ", "{0},{1},{2},{3}\r".format(IN_RELAYS[0], IN_RELAYS[1], 1, 0))

    async def sendRecipe(self, drinkIDs):
        for d_id in drinkIDs:
            await self.sendNextTransition(2, d_id)
        await self.sendNextTransition(3, SHAKE_COUNT)
        await self.sendNextTransition(4, 0)


async def run_connection(loop):
    async with TcpConnection(loop) as conn:
        await conn.initiateConnection()
        # relayString="{}, {}\r".format(RELAYS[0],8*RELAYS[1])
        # await conn.send_command("IOREAD ",relayString)
        # await asyncio.sleep(1.5)
        await asyncio.sleep(10)
        await conn.sendRecipe(TEST_RECIPE)
        # await conn.send_command("IOWRITE ", "{0},{1},{2},{3}\r".format(RELAYS[0],16,25,255))
        await asyncio.sleep(100)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    # Blocking call which returns when the hello_world() coroutine is done
    loop.run_until_complete(run_connection(loop))
    loop.close()
