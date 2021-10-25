import ctypes
import dataclasses
import datetime
import typing

from pyxivdata.common import AlmostStructureBase
from pyxivdata.network.ipc_opcodes import GameIpcOpcodes
from pyxivdata.network.ipc_structure import GameIpcDataIpcUpdateHpMpTp, GameIpcDataIpcSpawn, GameIpcDataIpcModelEquip, \
    GameIpcDataIpcPlayerStats, GameIpcDataIpcActorControl, GameIpcDataIpcEffectResult, GameIpcDataIpcStatusEffectList, \
    GameIpcDataCommonEffectType, GameIpcDataCommonStatusEffectEntryModificationInfo, GameIpcDataCommonStatusEffect
from pyxivdata.network.packet_structure import GameMessageHeader, GameIpcMessageHeader, GameMessageBundleHeader


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
    hp: typing.Optional[int] = None
    max_hp: typing.Optional[int] = None
    mp: typing.Optional[int] = None
    max_mp: typing.Optional[int] = None
    owner_id: typing.Optional[int] = None
    name: typing.Optional[str] = None
    bnpcname_id: typing.Optional[int] = None
    job: typing.Optional[int] = None
    level: typing.Optional[int] = None
    synced_level: typing.Optional[int] = None
    shield_ratio: typing.Optional[float] = None
    status_effects: typing.List[ActorStatusEffect] = dataclasses.field(default_factory=list)

    def update_status_effects_from_list(
            self,
            timestamp: datetime.datetime,
            effects: typing.Sequence[GameIpcDataCommonStatusEffect],
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
            updates: typing.Sequence[GameIpcDataCommonStatusEffectEntryModificationInfo],
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
class ActorManager:
    def __init__(self, opcodes: GameIpcOpcodes):
        self.__actors: typing.Dict[int, Actor] = {}
        self.__type2_map = {
            opcodes.UpdateHpMpTp: (self._on_update_hp_mp_tp, GameIpcDataIpcUpdateHpMpTp),
            opcodes.NpcSpawn: (self._on_spawn, GameIpcDataIpcSpawn),
            opcodes.PlayerSpawn: (self._on_spawn, GameIpcDataIpcSpawn),
            opcodes.ModelEquip: (self._on_model_equip, GameIpcDataIpcModelEquip),
            opcodes.PlayerStats: (self._on_player_stats, GameIpcDataIpcPlayerStats),
            opcodes.ActorControl: (self._on_actor_control, GameIpcDataIpcActorControl),
            opcodes.ActorControlSelf: (self._on_actor_control, GameIpcDataIpcActorControl),
            opcodes.ActorControlTarget: (self._on_actor_control, GameIpcDataIpcActorControl),
            opcodes.EffectResult: (self._on_effect_result, GameIpcDataIpcEffectResult),
            opcodes.StatusEffectList: (),
            opcodes.StatusEffectList2: (),
            opcodes.StatusEffectListBoss: (),
        }

    def __getitem__(self, actor_id: int) -> Actor:
        if actor_id not in self.__actors:
            self.__actors[actor_id] = Actor(actor_id)
        return self.__actors[actor_id]

    def feed(self, bundle_header: GameMessageBundleHeader, data: bytearray):
        if GameMessageHeader.from_buffer(data).type != GameMessageHeader.TYPE_IPC:
            return

        header = GameIpcMessageHeader.from_buffer(data)
        if header.type1 != GameIpcMessageHeader.TYPE1_IPC:
            return

        if header.type2 not in self.__type2_map:
            return

        data_type: typing.Type[AlmostStructureBase]
        cb, data_type = self.__type2_map.get(header.type2)
        cb(bundle_header, header, data_type.from_buffer(data[ctypes.sizeof(header):header.size]))

    def _on_update_hp_mp_tp(self, bundle_header: GameMessageBundleHeader, header: GameIpcMessageHeader,
                            data: GameIpcDataIpcUpdateHpMpTp):
        actor = self[header.actor_id]
        actor.last_updated_timestamp = bundle_header.timestamp
        actor.hp = data.hp
        actor.mp = data.mp

    def _on_spawn(self, bundle_header: GameMessageBundleHeader, header: GameIpcMessageHeader,
                  data: GameIpcDataIpcSpawn):
        actor = self[header.actor_id]
        actor.last_updated_timestamp = bundle_header.timestamp
        actor.name = data.name
        actor.owner_id = data.owner_id
        actor.bnpcname_id = data.bnpcname_id
        actor.level = data.level
        actor.job = data.job
        actor.max_hp = data.max_hp
        actor.max_mp = data.max_mp
        actor.hp = data.hp
        actor.mp = data.mp
        actor.update_status_effects_from_list(bundle_header.timestamp, data.status_effects)

    def _on_model_equip(self, bundle_header: GameMessageBundleHeader, header: GameIpcMessageHeader,
                        data: GameIpcDataIpcModelEquip):
        actor = self[header.actor_id]
        actor.last_updated_timestamp = bundle_header.timestamp
        actor.job = data.job
        actor.level = data.level

    def _on_player_stats(self, bundle_header: GameMessageBundleHeader, header: GameIpcMessageHeader,
                         data: GameIpcDataIpcSpawn):
        actor = self[header.actor_id]
        actor.last_updated_timestamp = bundle_header.timestamp
        actor.max_hp = data.max_hp
        actor.max_mp = data.max_mp

    def _on_actor_control(self, bundle_header: GameMessageBundleHeader, header: GameIpcMessageHeader,
                          data: GameIpcDataIpcActorControl):
        actor = self[header.actor_id]
        actor.last_updated_timestamp = bundle_header.timestamp
        if data.category == GameIpcDataIpcActorControl.CATEGORY_EFFECT_OVER_TIME:
            effect_type = GameIpcDataCommonEffectType(data.param2)
            amount = data.param3
            if effect_type == GameIpcDataCommonEffectType.Damage:
                actor.hp = max(0, min(actor.max_hp, actor.hp - amount))
            elif effect_type == GameIpcDataCommonEffectType.Heal:
                actor.hp = max(0, min(actor.max_hp, actor.hp + amount))

    def _on_effect_result(self, bundle_header: GameMessageBundleHeader, header: GameIpcMessageHeader,
                          data: GameIpcDataIpcEffectResult):
        actor = self[header.actor_id]
        actor.last_updated_timestamp = bundle_header.timestamp
        actor.hp = data.hp
        actor.max_hp = data.max_hp
        actor.mp = data.mp
        actor.shield_ratio = data.shield_percentage / 100.
        actor.update_status_effects_from_modification_info(bundle_header.timestamp, data.entries)

    def _on_status_effect_list(self, bundle_header: GameMessageBundleHeader, header: GameIpcMessageHeader,
                               data: GameIpcDataIpcStatusEffectList):
        actor = self[header.actor_id]
        actor.last_updated_timestamp = bundle_header.timestamp
        actor.level = data.level
        actor.job = data.job
        actor.max_hp = data.max_hp
        actor.max_mp = data.max_mp
        actor.hp = data.hp
        actor.mp = data.mp
        actor.shield_ratio = data.shield_percentage / 100.
        actor.update_status_effects_from_list(bundle_header.timestamp, data.status_effects)
