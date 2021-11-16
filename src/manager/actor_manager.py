import dataclasses
import datetime
import weakref

import math

from manager.stubs import IpcFeedTarget
from pyxivdata.installation.resource_reader import GameResourceReader
from pyxivdata.network.client_ipc import IpcRequestMove, IpcRequestMoveInstance
from pyxivdata.network.client_ipc.opcodes import ClientIpcOpcodes
from pyxivdata.network.packet import IpcMessageHeader, PacketHeader
from pyxivdata.network.server_ipc import *
from pyxivdata.network.server_ipc.actor_control import ActorControlClassJobChange, ActorControlAggro
from pyxivdata.network.server_ipc.common import StatusEffectEntryModificationInfo, StatusEffect
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
    spawn_id: typing.Optional[int] = None
    home_world_id: typing.Optional[int] = None
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
    zone_id: typing.Optional[int] = None
    bnpcname_id: typing.Optional[int] = None
    class_or_job: typing.Optional[int] = None
    level: typing.Optional[int] = None
    synced_level: typing.Optional[int] = None
    shield_ratio: typing.Optional[float] = None
    status_effects: typing.List[ActorStatusEffect] = dataclasses.field(default_factory=list)
    outgoing_enmity_per_actor: typing.Dict[int, int] = dataclasses.field(default_factory=dict)
    aggroed: bool = False

    def update_status_effect(self,
                             timestamp: datetime.datetime, index: int,
                             received_info: typing.Union[StatusEffect, StatusEffectEntryModificationInfo],
                             reader: GameResourceReader):
        while len(self.status_effects) <= index:
            self.status_effects.append(ActorStatusEffect())
        effect = self.status_effects[index]
        effect.effect_id = received_info.effect_id
        effect.param = received_info.param
        if received_info.duration > 0:
            effect.expiry = timestamp + datetime.timedelta(seconds=received_info.duration)
        else:
            effect.expiry = None
        effect.source_actor_id = received_info.source_actor_id

        if not effect.effect_id:
            return

        data_info = reader.get_status(received_info.effect_id)
        # TODO: calc "critical hit rate", (conditional) "damage dealt", (conditional) "damage taken"
        breakpoint()

    def update_status_effects_from_list(
            self,
            timestamp: datetime.datetime,
            effects: typing.Sequence[StatusEffect],
            reader: GameResourceReader,
    ):
        for i, effect in enumerate(effects):
            self.update_status_effect(timestamp, i, effect, reader)

    def update_status_effects_from_modification_info(
            self,
            timestamp: datetime.datetime,
            updates: typing.Sequence[StatusEffectEntryModificationInfo],
            reader: GameResourceReader,
    ):
        for effect in updates:
            self.update_status_effect(timestamp, effect.index, effect, reader)

    def distance(self, r: 'Actor') -> typing.Optional[float]:
        if self.x is None or r.x is None:
            return None
        return math.hypot(self.x - r.x, self.y - r.y)

    def __str__(self):
        return f"{self.name or '?'}({self.id:08x}) @{self.spawn_id}"


# noinspection DuplicatedCode
class ActorManager(IpcFeedTarget):
    __actors: typing.Union[typing.Dict[int, Actor], weakref.WeakValueDictionary]

    def __init__(self, resource_reader: GameResourceReader,
                 server_opcodes: ServerIpcOpcodes, client_opcodes: ClientIpcOpcodes):
        super().__init__(resource_reader, server_opcodes, client_opcodes)
        self.__root_actor = Actor(id=0xE0000000, name="(root)")
        self.__actors = weakref.WeakValueDictionary({
            0xE0000000: self.__root_actor,
        })
        self.__player = None
        self.__party: typing.List[typing.Union[Actor, str]] = []
        self.__party_id: typing.Optional[int] = None
        self.__alliance: typing.List[typing.Optional[Actor]] = []
        self.__spawns: typing.Dict[int, Actor] = {}

        @self._server_opcode_handler()
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: bytearray):
            if self.__player is None:
                self.__player = self[header.login_actor_id]

        @self._server_opcode_handler(server_opcodes.ActorStats)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcActorStats):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.hp = data.hp
            actor.mp = data.mp

        @self._server_opcode_handler(server_opcodes.PartyList)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcPartyList):
            self.__party = []
            self.__party_id = data.party_id
            for member in data.members[:data.party_size]:
                if member.character_id == 0:
                    self.__party.append(member.name)
                else:
                    actor = self[member.character_id]
                    actor.last_updated_timestamp = bundle_header.timestamp
                    # TODO: actor.home_world_id = member.home_world_id
                    actor.hp = member.hp
                    actor.max_hp = member.max_hp
                    actor.mp = member.mp
                    actor.max_mp = member.max_mp
                    actor.zone_id = member.zone_id
                    actor.class_or_job = member.class_or_job
                    actor.level = member.level
                    actor.name = member.name
                    self.__party.append(actor)

        @self._server_opcode_handler(server_opcodes.PartyModify)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcPartyModify):
            if data.party_size <= 1:
                self.__party.clear()
                self.__party_id = None

        @self._server_opcode_handler(server_opcodes.AllianceList)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcAllianceList):
            self.__alliance = []
            for member in data.members:
                actor = self[member.character_id]
                if actor is self.__root_actor:
                    self.__alliance.append(None)
                    continue
                self.__alliance.append(actor)
                actor.last_updated_timestamp = bundle_header.timestamp
                actor.class_or_job = member.class_or_job
                actor.hp = member.hp
                actor.max_hp = member.max_hp
                actor.name = member.name
                actor.home_world_id = member.home_world_id
            pass

        @self._server_opcode_handler(server_opcodes.ActorSpawn, server_opcodes.ActorSpawnNpc,
                                     server_opcodes.ActorSpawnNpc2)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader,
              data: typing.Union[IpcActorSpawn, IpcActorSpawnNpc]):
            self.__spawns[data.spawn_id] = actor = self[header.actor_id]
            if isinstance(data, IpcActorSpawn):
                actor.home_world_id = data.home_world_id
            else:
                actor.home_world_id = 0
            actor.spawn_id = data.spawn_id
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.name = data.name
            actor.owner_id = data.owner_id
            actor.bnpcname_id = data.bnpc_name
            actor.level = data.level
            actor.class_or_job = data.class_or_job
            actor.max_hp = data.max_hp
            actor.max_mp = data.max_mp
            actor.zone_id = self.__player.zone_id
            actor.hp = data.hp
            actor.mp = data.mp
            actor.update_status_effects_from_list(bundle_header.timestamp, data.status_effects,
                                                  self._resource_reader)
            actor.x = data.position_vector.x
            actor.y = data.position_vector.y
            actor.z = data.position_vector.z
            actor.rotation = data.rotation
            # print("Spawn", actor.spawn_id, actor.name)
            if isinstance(data, IpcActorSpawn):
                pass
            else:
                pass

        @self._server_opcode_handler(server_opcodes.ActorDespawn)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcActorDespawn):
            me = self[header.login_actor_id]
            msg = ["Despawn"]
            actor = self.__actors.get(data.actor_id, None)
            spawn = self.__spawns.get(data.spawn_id, None)
            if data.actor_id != 0:
                if data.actor_id in self.__actors:
                    msg.append(f"actor={self.__actors[data.actor_id].name}")
                    msg.append(f"distance={self.__actors[header.actor_id].distance(me)}")
                else:
                    msg.append(f"actor_id={data.actor_id:08x}")
            if data.spawn_id != 0:
                try:
                    d = self.__spawns[data.spawn_id]
                    msg.append(f"spawn={d.name}")
                    msg.append(f"distance={d.distance(me)}")
                except KeyError:
                    msg.append(f"spawn_id={data.spawn_id:08x}")
            if actor is not spawn:
                breakpoint()
            del self.__spawns[spawn.spawn_id]
            # print(f"Despawn: {actor.name}")
            pass  # TODO

        @self._server_opcode_handler(server_opcodes.ActorSetPos, server_opcodes.ActorMove)
        @self._client_opcode_handler(client_opcodes.RequestMoveInstance, client_opcodes.RequestMove)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader,
              data: typing.Union[IpcActorSetPos, IpcActorMove, IpcRequestMoveInstance, IpcRequestMove]):
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

        @self._server_opcode_handler(server_opcodes.AggroList)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcAggroList):
            actor = self.__actors[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.outgoing_enmity_per_actor.clear()
            for entry in data.entries[:data.entry_count]:
                actor.outgoing_enmity_per_actor[entry.actor_id] = entry.enmity_percent

        @self._server_opcode_handler(server_opcodes.InitZone)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcInitZone):
            self.__spawns.clear()
            actor = self.__actors[header.login_actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.zone_id = data.zone_id
            actor.x = data.position_vector.x
            actor.y = data.position_vector.y
            actor.z = data.position_vector.z

        @self._server_opcode_handler(server_opcodes.EffectResult)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcEffectResult):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.hp = data.hp
            actor.max_hp = data.max_hp
            actor.mp = data.mp
            actor.shield_ratio = data.shield_percentage / 100.
            actor.update_status_effects_from_modification_info(bundle_header.timestamp, data.entries[:data.entry_count],
                                                               self._resource_reader)

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
            actor.update_status_effects_from_list(bundle_header.timestamp, data.effects,
                                                  self._resource_reader)

        @self._actor_control_handler
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: ActorControlClassJobChange):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.class_or_job = data.class_or_job

        @self._actor_control_handler
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: ActorControlClassJobChange):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.class_or_job = data.class_or_job

        @self._actor_control_handler
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: ActorControlAggro):
            actor = self[header.actor_id]
            actor.last_updated_timestamp = bundle_header.timestamp
            actor.aggroed = data.aggroed

    def __getitem__(self, actor_id: int) -> Actor:
        actor = self.__actors.get(actor_id, None)
        if actor is None:
            self.__actors[actor_id] = actor = Actor(actor_id)
        return actor

    @property
    def party(self) -> typing.Sequence[typing.Union[Actor, str]]:
        return tuple(self.__party)

    @property
    def party_id(self):
        return self.__party_id
