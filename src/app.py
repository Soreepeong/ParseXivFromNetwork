import ctypes
import dataclasses
import io
import struct
import typing

import zlib

from manager.actor_manager import ActorManager
from manager.chat_manager import ChatManager
from manager.effect_manager import EffectManager
from pyxivdata.common import GameLanguage
from pyxivdata.installation.resource_reader import GameResourceReader
from pyxivdata.network.client_ipc.opcodes import ClientIpcOpcodes
from pyxivdata.network.packet import PacketHeader, MessageHeader, IpcMessageHeader
from pyxivdata.network.server_ipc import ServerIpcOpcodes, IpcDirectorUpdate, IpcPlaceWaymark, IpcPlacePresetWaymark


class Parser:
    def __init__(self):
        server_opcodes = ServerIpcOpcodes()
        client_opcodes = ClientIpcOpcodes()
        self.actor_manager = ActorManager(server_opcodes, client_opcodes)
        self.chat_manager = ChatManager(server_opcodes, client_opcodes, self.actor_manager)
        self.effect_manager = EffectManager(server_opcodes, client_opcodes, self.actor_manager)

    def feed_from_server(self, packet_header: PacketHeader, message_data: bytearray):
        self.actor_manager.feed_from_server(packet_header, message_data)
        self.chat_manager.feed_from_server(packet_header, message_data)
        self.effect_manager.feed_from_server(packet_header, message_data)

    def feed_from_client(self, packet_header: PacketHeader, message_data: bytearray):
        self.actor_manager.feed_from_client(packet_header, message_data)
        self.chat_manager.feed_from_client(packet_header, message_data)
        self.effect_manager.feed_from_client(packet_header, message_data)


def __main__():
    # path = r"D:\OneDrive\Misc\xivcapture\Network_22106_20211025\204.2.229.113.55027.log"
    path = r"D:\OneDrive\Misc\xivcapture\Network_22106_20211026\204.2.229.113.55027.log"
    # path = r"D:\OneDrive\Misc\xivcapture\Network_22106_20211026\124.150.157.26.55007.log"

    known_server_opcodes = [x.default for x in dataclasses.fields(ServerIpcOpcodes)]

    parser = Parser()
    fp: typing.Union[io.BytesIO]
    with open(path, "rb") as fp, GameResourceReader(default_language=[GameLanguage.English]) as res:
        while True:
            hdr = fp.read(5)
            if not hdr:
                break
            direction, length = struct.unpack("<cI", hdr)
            data = bytearray(length)
            fp.readinto(data)

            packet_header = PacketHeader.from_buffer(data)
            message_buffer = data[ctypes.sizeof(packet_header):]
            if packet_header.is_deflated:
                try:
                    message_buffer = bytearray(zlib.decompress(message_buffer))
                except zlib.error as e:
                    print(f"zlib error: {e}")
                    continue
            msgptr = 0
            while msgptr < len(message_buffer):
                message_header = MessageHeader.from_buffer(message_buffer, msgptr)
                if message_header.type == MessageHeader.TYPE_IPC:
                    ipc_header = IpcMessageHeader.from_buffer(message_buffer, msgptr)
                    ipc_data = message_buffer[msgptr + ctypes.sizeof(ipc_header):msgptr + ipc_header.size]
                    if direction == b'<':
                        parser.feed_from_server(packet_header, message_buffer[msgptr:msgptr + message_header.size])

                        if ipc_header.type2 == ServerIpcOpcodes.PlaceWaymark:
                            r = IpcPlaceWaymark.from_buffer(ipc_data)
                            breakpoint()
                        elif ipc_header.type2 == ServerIpcOpcodes.PlacePresetWaymark:
                            r = IpcPlacePresetWaymark.from_buffer(ipc_data)
                        elif ipc_header.type2 == ServerIpcOpcodes.DirectorUpdate:
                            r = IpcDirectorUpdate.from_buffer(ipc_data)
                            print("DirectorUpdate", r.sequence, r.branch, bytes(r.data).hex(" "))

                    elif direction == b'>':
                        parser.feed_from_client(packet_header, message_buffer[msgptr:msgptr + message_header.size])

                msgptr += message_header.size

    return 0


if __name__ == "__main__":
    exit(__main__())
