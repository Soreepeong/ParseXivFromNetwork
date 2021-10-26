from manager.actor_manager import ActorManager
from manager.stubs import IpcFeedTarget
from pyxivdata.network.client_ipc import IpcRequestChat, IpcRequestTell
from pyxivdata.network.client_ipc.opcodes import ClientIpcOpcodes
from pyxivdata.network.packet import PacketHeader, IpcMessageHeader
from pyxivdata.network.server_ipc import IpcChat, IpcChatParty
from pyxivdata.network.server_ipc.opcodes import ServerIpcOpcodes


class ChatManager(IpcFeedTarget):
    def __init__(self, server_opcodes: ServerIpcOpcodes, client_opcodes: ClientIpcOpcodes, actor_manager: ActorManager):
        super().__init__(server_opcodes, client_opcodes)
        self.__actors = actor_manager

        @self._server_opcode_handler(server_opcodes.Chat)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcChat):
            print(f"[{data.chat_type.name}] {data.name}: {data.message}")
            pass  # TODO

        @self._server_opcode_handler(server_opcodes.ChatParty)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcChatParty):
            print(f"[Party] {data.name} ({self.__actors[data.character_id]} @ {data.content_id}): {data.message}")
            pass

        @self._client_opcode_handler(client_opcodes.RequestChat)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcRequestChat):
            print(f"[{data.chat_type.name}] {self.__actors[header.login_actor_id]}!: {data.message}")
            pass

        @self._client_opcode_handler(client_opcodes.RequestTell)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcRequestTell):
            print(f">> {data.target_name}@{data.world_id}/{data.world_id_2}/{data.content_id}: {data.message}")
            pass
