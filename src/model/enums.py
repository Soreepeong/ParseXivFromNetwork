import enum


class NetworkEventType(enum.IntEnum):
    AddBuff = 0x1
    RefreshBuff = 0x2
    DeleteBuff = 0x3
    Chat = 0x104
    Tell = 0x105