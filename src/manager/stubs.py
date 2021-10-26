import collections
import ctypes
import inspect
import typing

from pyxivdata.network import server_ipc, client_ipc
from pyxivdata.network.client_ipc.opcodes import ClientIpcOpcodes
from pyxivdata.network.common import IpcStructure
from pyxivdata.network.packet import PacketHeader, MessageHeader, IpcMessageHeader
from pyxivdata.network.server_ipc import IpcActorControlStub
from pyxivdata.network.server_ipc.actor_control import ActorControlBase
from pyxivdata.network.server_ipc.opcodes import ServerIpcOpcodes

SupportedIpcDataTypes = typing.Union[
    typing.Type[ctypes.Structure],
    typing.Type[ctypes.LittleEndianStructure],
    typing.Type[ctypes.BigEndianStructure],
]

IpcCallbackType = typing.Callable[[PacketHeader, IpcMessageHeader, any], typing.NoReturn]
ActorControlCallbackType = typing.Callable[[PacketHeader, IpcMessageHeader, any], typing.NoReturn]

TYPE2_MAP_TYPE = typing.Dict[int, typing.List[typing.Tuple[IpcCallbackType, SupportedIpcDataTypes]]]


def _feed(bundle_header: PacketHeader, data: bytearray, type2_map: TYPE2_MAP_TYPE):
    if MessageHeader.from_buffer(data).type != MessageHeader.TYPE_IPC:
        return

    header = IpcMessageHeader.from_buffer(data)
    if header.type1 != IpcMessageHeader.TYPE1_IPC:
        return

    if header.type2 not in type2_map:
        return

    data_type: SupportedIpcDataTypes
    cb, data_type = type2_map.get(header.type2)
    cb(bundle_header, header, data_type.from_buffer(data[ctypes.sizeof(header):header.size]))


class IpcFeedTarget:
    __client_type2_map: TYPE2_MAP_TYPE
    __server_type2_map: TYPE2_MAP_TYPE
    __actor_control_map: typing.Dict[int, typing.List[typing.Tuple[ActorControlCallbackType,
                                                                   typing.Type[ActorControlBase]]]]

    def __init__(self, server_opcodes: ServerIpcOpcodes, client_opcodes: ClientIpcOpcodes):
        self.__opcodes = server_opcodes
        self.__client_type2_map = collections.defaultdict(list)
        self.__server_type2_map = collections.defaultdict(list)
        self.__actor_control_map = collections.defaultdict(list)

        self.__server_opcode_type_map = {
            getattr(server_opcodes, t.OPCODE_FIELD): t
            for t in vars(server_ipc).values()
            if isinstance(t, type) and issubclass(t, IpcStructure) and t.OPCODE_FIELD is not None
        }
        self.__client_opcode_type_map = {
            getattr(client_opcodes, t.OPCODE_FIELD): t
            for t in vars(client_ipc).values()
            if isinstance(t, type) and issubclass(t, IpcStructure) and t.OPCODE_FIELD is not None
        }

        @self._server_opcode_handler(server_opcodes.ActorControl)
        @self._server_opcode_handler(server_opcodes.ActorControlSelf)
        @self._server_opcode_handler(server_opcodes.ActorControlTarget)
        def _(bundle_header: PacketHeader, header: MessageHeader, data: IpcActorControlStub):
            if data.type not in self.__actor_control_map:
                return

            data_type: typing.Type[ActorControlBase]
            cb, data_type = self.__actor_control_map.get(data.type)
            cb(bundle_header, header, data_type(data[ctypes.sizeof(header):header.size]))

    def feed_from_server(self, bundle_header: PacketHeader, data: bytearray):
        return _feed(bundle_header, data, self.__server_type2_map)

    def feed_from_client(self, bundle_header: PacketHeader, data: bytearray):
        return _feed(bundle_header, data, self.__client_type2_map)

    def _opcode_handler(self, direction: bool, *opcodes: int):
        type_ = type

        def wrapper(cb: IpcCallbackType):
            nonlocal type_
            if type_ is None:
                type_ = list(inspect.signature(cb).parameters.values())[2]
            for opcode in opcodes:
                type2_map = self.__server_type2_map if direction else self.__client_type2_map
                type2_map[opcode].append((cb, self.__server_opcode_type_map[opcode]))
            return cb

        return wrapper

    def _server_opcode_handler(self, *opcodes: int):
        return self._opcode_handler(True, *opcodes)

    def _client_opcode_handler(self, *opcodes: int):
        return self._opcode_handler(False, *opcodes)

    # noinspection PyShadowingBuiltins
    def _actor_control_handler(self, type: typing.Union[typing.Type[ActorControlBase], callable, None] = None):
        type_ = type

        def wrapper(cb: ActorControlCallbackType):
            nonlocal type_
            if type_ is None:
                type_ = list(inspect.signature(cb).parameters.values())[2].annotation
            self.__actor_control_map[type_.TYPE].append((cb, type_))
            return cb

        if callable(type_):
            cb_ = type_
            type_ = None
            return wrapper(cb_)
        else:
            return wrapper
