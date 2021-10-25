from pyxivdata.network.ipc_opcodes import GameIpcOpcodes


class EffectManager:
    def __init__(self, opcodes: GameIpcOpcodes):
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