import dataclasses
import datetime

from manager.stubs import IpcFeedTarget
from pyxivdata.network.client_ipc.opcodes import ClientIpcOpcodes
from pyxivdata.network.packet import IpcMessageHeader, PacketHeader
from pyxivdata.network.server_ipc import *
from pyxivdata.network.server_ipc.actor_control import ActorControlClassJobChange, ActorControlEffectOverTime
from pyxivdata.network.server_ipc.common import StatusEffectEntryModificationInfo, StatusEffect
from pyxivdata.network.enums import EffectType
from pyxivdata.network.server_ipc.opcodes import ServerIpcOpcodes


@dataclasses.dataclass
class ActorStatusEffect:
    effect_id: int = 0
    param: int = 0
    expiry: typing.Optional[datetime.datetime] = None
    source_actor_id: int = 0


@dataclasses.dataclass
class Actor:
    id: int
    last_updated_timestamp: typing.Optional[datetime.datetime] = None
    x: typing.Optional[float] = None
    y: typing.Optional[float] = None
    z: typing.Optional[float] = None
    rotation: typing.Optional[float] = None
    hp: typing.Optional[int] = None
    max_hp: typing.Optional[int] = None
    mp: typing.Optional[int] = None
    max_mp: typing.Optional[int] = None
    owner_id: typing.Optional[int] = None
    name: typing.Optional[str] = None
    bnpcname_id: typing.Optional[int] = None
    class_or_job: typing.Optional[int] = None
    level: typing.Optional[int] = None
    synced_level: typing.Optional[int] = None
    shield_ratio: typing.Optional[float] = None
    status_effects: typing.List[ActorStatusEffect] = dataclasses.field(default_factory=list)

    def update_status_effects_from_list(
            self,
            timestamp: datetime.datetime,
            effects: typing.Sequence[StatusEffect],
    ):
        for i, effect in enumerate(effects):
            while len(self.status_effects) <= i:
                self.status_effects.append(ActorStatusEffect())
            t = self.status_effects[i]
            t.effect_id = effect.effect_id
            t.param = effect.param
            if effect.duration > 0:
                t.expiry = timestamp + datetime.timedelta(seconds=effect.duration)
            else:
                t.expiry = None
            t.source_actor_id = effect.source_actor_id

    def update_status_effects_from_modification_info(
            self,
            timestamp: datetime.datetime,
            updates: typing.Sequence[StatusEffectEntryModificationInfo],
    ):
        for effect in updates:
            while len(self.status_effects) <= effect.index:
                self.status_effects.append(ActorStatusEffect())
            t = self.status_effects[effect.index]
            t.effect_id = effect.effect_id
            t.param = effect.param
            if effect.duration > 0:
                t.expiry = timestamp + datetime.timedelta(seconds=effect.duration)
            else:
                t.expiry = None
            t.source_actor_id = effect.source_actor_id


# noinspection DuplicatedCode
class ActorManager(IpcFeedTarget):
    def __init__(self, server_opcodes: ServerIpcOpcodes, client_opcodes: ClientIpcOpcodes):
        super().__init__(server_opcodes, client_opcodes)
        self.__actors: typing.Dict[int, Actor] = {
            0xE0000000: Actor(id=0xE0000000, name="(root)")
        }

        @self._server_opcode_handler(server_opcodes.ActorStats)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcActorStats):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.hp = data.hp
            actor.mp = data.mp

        @self._server_opcode_handler(server_opcodes.ActorSpawn, server_opcodes.ActorSpawnNpc,
                                     server_opcodes.ActorSpawnNpc2)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader,
              data: typing.Union[IpcActorSpawn, IpcActorSpawnNpc]):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.name = data.name
            actor.owner_id = data.owner_id
            actor.bnpcname_id = data.bnpc_name
            actor.level = data.level
            actor.class_or_job = data.class_or_job
            actor.max_hp = data.max_hp
            actor.max_mp = data.max_mp
            actor.hp = data.hp
            actor.mp = data.mp
            actor.update_status_effects_from_list(bundle_header.timestamp, data.status_effects)
            actor.x = data.position_vector.x
            actor.y = data.position_vector.y
            actor.z = data.position_vector.z
            actor.rotation = data.rotation

        @self._server_opcode_handler(server_opcodes.ActorDespawn)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcActorDespawn):
            print(f"Despawn: current={self.__actors[header.actor_id]} actor={data.actor_id} spawn={data.spawn_id}")
            pass  # TODO

        @self._server_opcode_handler(server_opcodes.ActorSetPos, server_opcodes.ActorMove)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: typing.Union[IpcActorSetPos, IpcActorMove]):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.x = data.position_vector.x
            actor.y = data.position_vector.y
            actor.z = data.position_vector.z
            actor.rotation = data.rotation

        @self._server_opcode_handler(server_opcodes.ActorModelEquip)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcActorModelEquip):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.class_or_job = data.class_or_job
            actor.level = data.level

        @self._server_opcode_handler(server_opcodes.PlayerParams)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcPlayerParams):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.max_hp = data.hp
            actor.max_mp = data.mp

        @self._server_opcode_handler(server_opcodes.EffectResult)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcEffectResult):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.hp = data.hp
            actor.max_hp = data.max_hp
            actor.mp = data.mp
            actor.shield_ratio = data.shield_percentage / 100.
            actor.update_status_effects_from_modification_info(bundle_header.timestamp, data.entries[:data.entry_count])

        @self._server_opcode_handler(server_opcodes.ActorStatusEffectList, server_opcodes.ActorStatusEffectList2,
                                     server_opcodes.ActorStatusEffectListBoss)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcActorStatusEffectList):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.level = data.level
            actor.class_or_job = data.class_or_job
            actor.max_hp = data.max_hp
            actor.max_mp = data.max_mp
            actor.hp = data.hp
            actor.mp = data.mp
            actor.shield_ratio = data.shield_percentage / 100.
            actor.update_status_effects_from_list(bundle_header.timestamp, data.effects)

        @self._actor_control_handler
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: ActorControlClassJobChange):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.class_or_job = data.class_or_job

        @self._actor_control_handler
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: ActorControlEffectOverTime):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            if data.effect_type == EffectType.Damage:
                actor.hp = max(0, min(actor.max_hp, actor.hp - data.amount))
            elif data.effect_type == EffectType.Heal:
                actor.hp = max(0, min(actor.max_hp, actor.hp + data.amount))

    def __getitem__(self, actor_id: int) -> Actor:
        if actor_id not in self.__actors:
            self.__actors[actor_id] = Actor(actor_id)
        return self.__actors[actor_id]
