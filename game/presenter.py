from retroarch_overlay.models import PanelAction, PanelRow, PanelSection

from .battle import ev_awards, experience_awards
from .contest import PokeblockState, ribbon_names
from .state import BattlePokemonState, PokemonState, STAT_NAMES


def display_constant(value: str, prefix: str) -> str:
    return " ".join(word.capitalize() for word in value.removeprefix(prefix).split("_"))


class EmeraldPresenter:
    def __init__(
        self,
        species_info: dict[str, dict[str, object]],
        item_names: dict[int, str],
        move_info: dict[int, dict[str, object]],
        ability_names: dict[int, str],
        type_chart: tuple[tuple[int, int, int], ...],
    ) -> None:
        self._species_info = species_info
        self._item_names = item_names
        self._move_info = move_info
        self._ability_names = ability_names
        self._type_chart = {
            (attack, defense): multiplier / 10
            for attack, defense, multiplier in type_chart
        }

    def party_section(self, party: tuple[PokemonState, ...]) -> PanelSection | None:
        if not party:
            return None
        rows = tuple(
            PanelRow(
                f"{display_constant(member.species, 'SPECIES_')} · Lv {member.level} · "
                f"HP {member.hp}/{member.max_hp} · {member.nature}"
            )
            for member in party
        )
        details = []
        for member in party:
            name = display_constant(member.species, "SPECIES_")
            metadata = self._species_info.get(member.species, {})
            ability_ids = metadata.get("abilities", [0, 0])
            ability_id = int(ability_ids[min(member.ability_slot, len(ability_ids) - 1)])
            ability = self._ability_names.get(ability_id, f"Ability {ability_id}")
            item = self._item_names.get(member.held_item_id, f"Item {member.held_item_id}") if member.held_item_id else "None"
            details.append(PanelRow(f"{name} · Lv {member.level}".upper()))
            details.append(PanelRow(f"HP {member.hp}/{member.max_hp} · {member.nature} · {ability}"))
            details.append(PanelRow(f"Held: {item} · Friendship {member.friendship} · {'Traded' if member.is_traded else 'Original Trainer'}"))
            for move_id, pp in zip(member.moves, member.pp):
                if not move_id:
                    continue
                move = self._move_info.get(move_id, {})
                details.append(PanelRow(f"{move.get('name', f'Move {move_id}')} · PP {pp}/{move.get('pp', '?')}"))
            details.append(PanelRow(f"EVs · {self._stat_values(member.evs)} · total {sum(member.evs)}/510"))
            details.append(PanelRow(f"IVs · {self._stat_values(member.ivs)}"))
            details.append(PanelRow(f"Pokérus · {member.pokerus_state}"))
        return PanelSection(
            f"Party · {len(party)}",
            rows,
            preview_limit=3,
            actions=(PanelAction("OPEN PARTY", "Pokemon Emerald Party", tuple(details)),),
            priority=10,
            role="party",
            compact_rows=(PanelRow(f"{len(party)} Pokémon · {sum(member.hp > 0 for member in party)} able"),),
        )

    def contest_section(
        self,
        party: tuple[PokemonState, ...],
        pokeblocks: tuple[PokeblockState, ...],
    ) -> PanelSection | None:
        if not party:
            return None
        details = []
        total_ribbons = 0
        for member in party:
            name = display_constant(member.species, "SPECIES_")
            total_ribbons += member.ribbon_count
            details.append(PanelRow(f"{name} · CONTEST".upper()))
            details.append(
                PanelRow(
                    " · ".join(
                        f"{label} {value}"
                        for label, value in zip(("Cool", "Beauty", "Cute", "Smart", "Tough"), member.contest)
                    )
                )
            )
            details.append(PanelRow(f"Sheen {member.sheen} · Ribbons {member.ribbon_count}"))
            if member.species == "SPECIES_FEEBAS":
                state = "READY" if member.contest[1] >= 170 else f"need {170 - member.contest[1]}"
                details.append(PanelRow(f"Milotic Beauty · {member.contest[1]}/170 · {state}"))
            ribbons = ribbon_names(member)
            if ribbons:
                details.append(PanelRow("Ribbons · " + " · ".join(ribbons)))
        details.append(PanelRow(f"POKEBLOCK CASE · {len(pokeblocks)}/40"))
        for block in pokeblocks:
            details.append(
                PanelRow(
                    f"Slot {block.slot + 1} · {block.color} · "
                    f"Spicy {block.spicy} · Dry {block.dry} · Sweet {block.sweet} · "
                    f"Bitter {block.bitter} · Sour {block.sour} · Feel {block.feel}"
                )
            )
        return PanelSection(
            "Contests & ribbons",
            (PanelRow(f"Ribbons {total_ribbons} · Pokéblocks {len(pokeblocks)}/40"),),
            actions=(PanelAction("OPEN CONTEST DETAILS", "Contest and Ribbon Progress", tuple(details)),),
            priority=40,
            role="goals",
        )

    def battle_reward_section(
        self,
        opponents: tuple[BattlePokemonState, ...],
        party: tuple[PokemonState, ...],
        participants: frozenset[int],
        *,
        trainer_battle: bool,
    ) -> PanelSection | None:
        rows = []
        for opponent in opponents:
            metadata = self._species_info.get(opponent.species)
            if not metadata:
                continue
            ev_yield = tuple(int(value) for value in metadata.get("ev_yield", (0,) * 6))
            ev_text = self._positive_stat_values(ev_yield)
            name = display_constant(opponent.species, "SPECIES_")
            rows.append(PanelRow(f"{name} · {ev_text or 'No EVs'}"))
            exp = experience_awards(
                int(metadata.get("exp_yield", 0)),
                opponent.level,
                party,
                participants,
                trainer_battle=trainer_battle,
            )
            ev = ev_awards(ev_yield, party, participants)
            for member in party:
                if member.slot not in exp and member.slot not in ev:
                    continue
                gains = self._positive_stat_values(ev.get(member.slot, (0,) * 6))
                rows.append(
                    PanelRow(
                        f"{display_constant(member.species, 'SPECIES_')} · "
                        f"+{exp.get(member.slot, 0)} XP"
                        f"{f' · +{gains}' if gains else ''}"
                    )
                )
        if not rows:
            return None
        return PanelSection(
            "Rewards if defeated",
            tuple(rows),
            priority=5,
            role="urgent",
            compact_rows=tuple(rows[:2]),
        )

    def opponent_team_section(
        self, opponents: tuple[PokemonState, ...]
    ) -> PanelSection | None:
        if not opponents:
            return None
        rows = tuple(
            PanelRow(
                f"{display_constant(member.species, 'SPECIES_')} · Lv {member.level} · "
                f"HP {member.hp}/{member.max_hp}"
            )
            for member in opponents
        )
        details = []
        for member in opponents:
            name = display_constant(member.species, "SPECIES_")
            details.append(PanelRow(f"{name} · Lv {member.level}".upper()))
            details.append(PanelRow(f"HP {member.hp}/{member.max_hp} · {member.nature}"))
            if member.held_item_id:
                details.append(
                    PanelRow(
                        f"Held: {self._item_names.get(member.held_item_id, f'Item {member.held_item_id}')}"
                    )
                )
            for move_id, pp in zip(member.moves, member.pp):
                if not move_id:
                    continue
                move = self._move_info.get(move_id, {})
                details.append(
                    PanelRow(
                        f"{move.get('name', f'Move {move_id}')} · PP {pp}/{move.get('pp', '?')}"
                    )
                )
        return PanelSection(
            f"Opponent team · {len(opponents)}",
            rows,
            preview_limit=3,
            actions=(
                PanelAction("OPEN OPPONENT TEAM", "Opponent Team", tuple(details)),
            ),
            priority=4,
            role="urgent",
            compact_rows=(PanelRow(f"{len(opponents)} Pokémon loaded"),),
        )

    def battle_advice_section(
        self,
        active_opponents: tuple[BattlePokemonState, ...],
        enemy_party: tuple[PokemonState, ...],
        party: tuple[PokemonState, ...],
    ) -> PanelSection | None:
        rows = []
        for opponent in active_opponents:
            candidates = []
            for member in party:
                if member.hp <= 0 or member.is_egg:
                    continue
                for move_id in member.moves:
                    move = self._move_info.get(move_id)
                    if not move or int(move.get("power", 0)) <= 0:
                        continue
                    multiplier = self.type_effectiveness(
                        int(move.get("type", -1)), opponent.types
                    )
                    candidates.append(
                        (
                            multiplier,
                            int(move.get("power", 0)),
                            member.stats[2],
                            member,
                            str(move.get("name", f"Move {move_id}")),
                        )
                    )
            if candidates:
                multiplier, _, speed, member, move_name = max(
                    candidates, key=lambda value: value[:3]
                )
                speed_note = ""
                if speed and opponent.stats[2]:
                    speed_note = " · likely faster" if speed > opponent.stats[2] else " · likely slower"
                rows.append(
                    PanelRow(
                        f"{display_constant(opponent.species, 'SPECIES_')} · "
                        f"{display_constant(member.species, 'SPECIES_')} → {move_name} · "
                        f"{multiplier:g}x{speed_note}"
                    )
                )

        threats = []
        for enemy in enemy_party:
            for move_id in enemy.moves:
                move = self._move_info.get(move_id)
                if not move or int(move.get("power", 0)) <= 0:
                    continue
                move_type = int(move.get("type", -1))
                for member in party:
                    metadata = self._species_info.get(member.species, {})
                    types = tuple(int(value) for value in metadata.get("types", ()))
                    multiplier = self.type_effectiveness(move_type, types)
                    if multiplier > 1:
                        threats.append(
                            (
                                multiplier,
                                int(move.get("power", 0)),
                                enemy,
                                member,
                                str(move.get("name", f"Move {move_id}")),
                            )
                        )
        if threats:
            multiplier, _, enemy, member, move_name = max(
                threats, key=lambda value: value[:2]
            )
            rows.append(
                PanelRow(
                    f"Threat · {display_constant(enemy.species, 'SPECIES_')} → "
                    f"{display_constant(member.species, 'SPECIES_')} · {move_name} · "
                    f"{multiplier:g}x"
                )
            )
        if not rows:
            return None
        return PanelSection(
            "Battle advice",
            tuple(rows),
            priority=2,
            role="urgent",
            compact_rows=tuple(rows[:2]),
        )

    def type_effectiveness(
        self, attack_type: int, defense_types: tuple[int, ...]
    ) -> float:
        multiplier = 1.0
        for defense_type in dict.fromkeys(defense_types):
            multiplier *= self._type_chart.get((attack_type, defense_type), 1.0)
        return multiplier

    @staticmethod
    def _stat_values(values: tuple[int, ...]) -> str:
        return " · ".join(f"{name} {value}" for name, value in zip(STAT_NAMES, values))

    @staticmethod
    def _positive_stat_values(values: tuple[int, ...]) -> str:
        return " · ".join(
            f"{value} {name}"
            for name, value in zip(STAT_NAMES, values)
            if value
        )