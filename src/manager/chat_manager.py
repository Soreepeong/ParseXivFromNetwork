import ctypes
import typing

from manager.actor_manager import ActorManager
from manager.stubs import IpcFeedTarget
from pyxivdata.escaped_string import SeString
from pyxivdata.installation.resource_reader import GameResourceReader
from pyxivdata.network.client_ipc import IpcRequestChat, IpcRequestTell, IpcRequestChatParty
from pyxivdata.network.client_ipc.opcodes import ClientIpcOpcodes
from pyxivdata.network.enums import ChatType
from pyxivdata.network.packet import PacketHeader, IpcMessageHeader
from pyxivdata.network.server_ipc import IpcChat, IpcChatParty, IpcChatTell, IpcNpcYell, IpcContentTextData
from pyxivdata.network.server_ipc.opcodes import ServerIpcOpcodes


class ChatManager(IpcFeedTarget):
    def __init__(self, resource_reader: GameResourceReader,
                 server_opcodes: ServerIpcOpcodes, client_opcodes: ClientIpcOpcodes,
                 actor_manager: ActorManager):
        super().__init__(resource_reader, server_opcodes, client_opcodes)
        self.__actors = actor_manager

        @self._server_opcode_handler(server_opcodes.NpcYell)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcNpcYell):
            for fn in ("BNpcName", "ENpcResident"):  # TODO: how to distinguish?
                try:
                    bnpcname = resource_reader.get_excel_string(fn, data.name_id, 0)
                    break
                except KeyError:
                    pass
            else:
                bnpcname = "?"
                fn = "?"
            txt = resource_reader.get_excel_string("NpcYell", data.row_id, 10)
            actor = self.__actors[data.actor_id]
            print(f"[NpcYell] {actor}({fn}:{data.name_id}={bnpcname}): {data.row_id}={txt}")

        @self._server_opcode_handler(server_opcodes.ContentTextData)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcContentTextData):
            bnpcname = resource_reader.get_bnpc_name(data.bnpcname_id)
            for fn in ("PublicContentTextData", "InstanceContentTextData"):  # TODO: how to distinguish?
                try:
                    txt = resource_reader.get_excel_string(fn, data.row_id, 0)
                    break
                except KeyError:
                    pass
            else:
                txt = "?"
                fn = "?"
            actor = self.__actors[data.actor_id]
            print(f"[ContentTextData] someobjid={data.some_object_id:08x} "
                  f"{actor}({data.bnpcname_id}={bnpcname}): {fn}:{data.row_id}={txt} ({data.duration_ms}ms)")

        @self._server_opcode_handler(server_opcodes.Chat)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcChat):
            self._on_chat(data.chat_type, data.character_id, data.name, data.world_id, data.message)

        @self._server_opcode_handler(server_opcodes.ChatParty)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcChatParty):
            if data.party_id == self.__actors.party_id:
                self._on_chat(ChatType.Party, data.character_id, data.name, data.world_id, data.message)
            else:
                # apparently FC chat also comes this way
                self._on_chat(ChatType.FreeCompany, data.character_id, data.name, data.world_id, data.message)

        @self._server_opcode_handler(server_opcodes.ChatTell)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcChatTell):
            self._on_chat(ChatType.TellReceive, None, data.name, data.world_id, data.message)

        @self._client_opcode_handler(client_opcodes.RequestChat)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcRequestChat):
            me = self.__actors[header.login_actor_id]
            self._on_chat(data.chat_type, me.id, me.name, me.home_world_id, data.message)

        @self._client_opcode_handler(client_opcodes.RequestChatParty)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcRequestChatParty):
            me = self.__actors[header.login_actor_id]
            if data.party_id == self.__actors.party_id:
                self._on_chat(ChatType.Party, me.id, me.name, me.home_world_id, data.message)
            else:
                self._on_chat(ChatType.FreeCompany, me.id, me.name, me.home_world_id, data.message)

        @self._client_opcode_handler(client_opcodes.RequestTell)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcRequestTell):
            me = self.__actors[header.login_actor_id]
            self._on_chat(ChatType.Tell, me.id, me.name, me.home_world_id, data.message, data.target_name,
                          data.world_id)

    def _on_chat(self, chat_type: ChatType, from_id: typing.Optional[int], from_name: str, from_world: int,
                 message: SeString,
                 to_name: typing.Optional[str] = None, to_world: typing.Optional[int] = None):
        message.set_sheet_reader(self._resource_reader.excels.__getitem__)
        if chat_type == ChatType.Tell:
            print(f"{from_name}@{self._resource_reader.get_world_name(from_world)} >> {repr(message)}")
        elif chat_type == ChatType.TellReceive:
            print(f">> {from_name}@{self._resource_reader.get_world_name(from_world)}: {repr(message)}")
        else:
            print(f"[{chat_type.name}] {from_name}@{self._resource_reader.get_world_name(from_world)}: {repr(message)}")
