import datetime

from manager.actor_manager import ActorManager
from manager.chat_manager import ChatManager
from manager.effect_manager import EffectManager
from pyxivdata.network.client_ipc.opcodes import ClientIpcOpcodes
from pyxivdata.network.server_ipc import ServerIpcOpcodes


def __main__():
    server_opcodes = ServerIpcOpcodes()
    client_opcodes = ClientIpcOpcodes()
    actor_manager = ActorManager(server_opcodes, client_opcodes)
    effect_manager = EffectManager(server_opcodes, client_opcodes, actor_manager)
    chat_manager = ChatManager(server_opcodes, client_opcodes, actor_manager)

    # TODO: use pip "pyshark" to test from wireshark capture file

    return 0


if __name__ == "__main__":
    exit(__main__())
