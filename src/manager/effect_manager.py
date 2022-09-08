import dataclasses
import datetime

from manager.actor_manager import ActorManager, Actor
from manager.stubs import IpcFeedTarget
from pyxivdata.installation.resource_reader import GameResourceReader
from pyxivdata.network.client_ipc.opcodes import ClientIpcOpcodes
from pyxivdata.network.packet import PacketHeader, IpcMessageHeader
from pyxivdata.network.server_ipc import *
from pyxivdata.network.server_ipc.actor_control import ActorControlEffectOverTime, ActorControlDeath
from pyxivdata.network.server_ipc.common import ActionEffect
from pyxivdata.network.server_ipc.opcodes import ServerIpcOpcodes


@dataclasses.dataclass
class PendingEffect:
    timestamp: datetime.datetime
    source_actor: Actor
    effect: IpcEffectStub
    effects_per_target: typing.Dict[int, typing.List[ActionEffect]]


class EffectManager(IpcFeedTarget):
    def __init__(self, resource_reader: GameResourceReader,
                 server_opcodes: ServerIpcOpcodes, client_opcodes: ClientIpcOpcodes,
                 actor_manager: ActorManager):
        super().__init__(resource_reader, server_opcodes, client_opcodes)
        self._actors = actor_manager
        self._pending_effects: typing.Dict[int, PendingEffect] = {}
        self._battles = []

        @self._server_opcode_handler(server_opcodes.Effect01, server_opcodes.Effect08, server_opcodes.Effect16,
                                     server_opcodes.Effect24, server_opcodes.Effect32)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcEffectStub):
            self._pending_effects[data.global_sequence_id] = PendingEffect(
                timestamp=bundle_header.timestamp,
                source_actor=self._actors[header.actor_id],
                effect=data,
                effects_per_target=data.valid_known_effects_per_target,
            )

        @self._server_opcode_handler(server_opcodes.EffectResult)
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: IpcEffectResult):
            try:
                pending_effect = self._pending_effects[data.global_sequence_id]
                effects = pending_effect.effects_per_target.pop(header.actor_id)
                if not pending_effect.effects_per_target:
                    del self._pending_effects[data.global_sequence_id]
            except KeyError:
                # TODO: log
                return

            source_actor = pending_effect.source_actor
            timestamp = bundle_header.timestamp
            for effect in effects:
                target_actor = source_actor if effect.effect_on_source else self._actors[header.actor_id]

                self._on_effect(timestamp, source_actor, target_actor, pending_effect.effect, effect)

        @self._actor_control_handler
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: ActorControlEffectOverTime):
            self._on_effect_over_time(bundle_header.timestamp, self._actors[header.actor_id],
                                      data.buff_id, data.effect_type, data.amount,
                                      None if data.source_actor_id == 0 else self._actors[data.source_actor_id])

        @self._actor_control_handler
        def _(bundle_header: PacketHeader, header: IpcMessageHeader, data: ActorControlDeath):
            for seq_id, pending_effect in list(self._pending_effects.items()):
                if pending_effect.source_actor.id == header.actor_id:
                    # Effect won't take effect if the source actor is defeated at the time of effect application.
                    del self._pending_effects[seq_id]
            pass

    def _on_effect(self, timestamp: datetime.datetime, source: Actor, target: Actor,
                   pending_effect: IpcEffectStub, effect: ActionEffect):
        if effect.known_effect_type not in (EffectType.Damage, EffectType.Heal):
            return

        d = [
            f"{timestamp:%Y-%m-%d %H:%M:%S.%f}",
            f"{source.format(self._resource_reader, self._actors[source.owner_id])}",
            f"=> {target.format(self._resource_reader, self._actors[target.owner_id])}",
            f"{effect.value * (-1 if effect.known_effect_type == EffectType.Damage else 1):>+7}",
            f"{self._resource_reader.get_action_name(pending_effect.action_id, fallback_format='?')}({pending_effect.action_id})",
            f"=> {target.hp:,}/{target.max_hp:,} ({100 * target.hp / target.max_hp:.02f}%)"
        ]
        print(*d)
        pass  # TODO

    def _on_effect_over_time(self, timestamp: datetime.datetime, target: Actor,
                             buff_id: int, effect_type: int, amount: int, source: typing.Optional[Actor]):
        if effect_type not in (EffectType.Damage, EffectType.Heal):
            return

        d = [
            f"{timestamp:%Y-%m-%d %H:%M:%S.%f}",
            f"{'?' if source is None else source.format(self._resource_reader, None if source.owner_id is None else self._actors[source.owner_id])}",
            f"=> {target.format(self._resource_reader, self._actors[target.owner_id])}",
            f"{amount * (-1 if effect_type == EffectType.Damage else 1):>+7}",
            f"{self._resource_reader.get_status_effect_name(buff_id, fallback_format='?')}({buff_id}, *)" if buff_id else "?(*)",
            f"=> {target.hp:,}/{target.max_hp:,} ({100 * target.hp / target.max_hp:.02f}%)"
        ]
        print(*d)
        pass  # TODO
