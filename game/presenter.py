from collections.abc import Callable

from retroarch_overlay.models import PanelAction, PanelChip, PanelRow, PanelSection

from .battle import ev_awards, experience_awards
from .contest import PokeblockState, ribbon_names
from .damage import (
    PHYSICAL_TYPES,
    active_battle_state,
    attacker_offense,
    damage_range,
    defender_defense,
    effectiveness_value,
    hits_to_ko,
    staged_stat,
    type_multipliers,
)
from .state import BattlePokemonState, PokemonState, STAT_NAMES


def display_constant(value: str, prefix: str) -> str:
    return " ".join(word.capitalize() for word in value.removeprefix(prefix).split("_"))


# The classic Gen III type palette, readable on light and dark backgrounds.
TYPE_CHIP_COLORS = {
    0: "#8a8a59", 1: "#c03028", 2: "#a890f0", 3: "#a040a0", 4: "#e0c068",
    5: "#b8a038", 6: "#a8b820", 7: "#705898", 8: "#b8b8d0", 10: "#f08030",
    11: "#6890f0", 12: "#78c850", 13: "#d3b136", 14: "#f85888", 15: "#98d8d8",
    16: "#7038f8", 17: "#705848",
}

TYPE_CHIP_NAMES = {
    0: "NRM", 1: "FTG", 2: "FLY", 3: "PSN", 4: "GRD", 5: "RCK", 6: "BUG",
    7: "GHO", 8: "STL", 10: "FIR", 11: "WTR", 12: "GRS", 13: "ELE",
    14: "PSY", 15: "ICE", 16: "DRG", 17: "DRK",
}

STATUS_CHIPS = (
    (0x7, "SLP", "#8a8a59"),
    (0x80, "TOX", "#7a2f7a"),
    (0x8, "PSN", "#a040a0"),
    (0x10, "BRN", "#f08030"),
    (0x20, "FRZ", "#5b9bd0"),
    (0x40, "PAR", "#c9a418"),
)


def type_chip(type_id: int) -> PanelChip | None:
    name = TYPE_CHIP_NAMES.get(type_id)
    if name is None:
        return None
    return PanelChip(name, TYPE_CHIP_COLORS.get(type_id, "#687064"))


def status_chips(status: int) -> tuple[PanelChip, ...]:
    return tuple(
        PanelChip(label, color)
        for mask, label, color in STATUS_CHIPS
        if status & mask
    )


def effectiveness_chip(value: float) -> PanelChip:
    if value >= 4:
        return PanelChip("4X", "#1d7a3e")
    if value >= 2:
        return PanelChip("2X", "#27824a")
    if value >= 1:
        return PanelChip("1X", "#687064")
    if value > 0.26:
        return PanelChip("1/2X", "#a86e14")
    if value > 0:
        return PanelChip("1/4X", "#b3552a")
    return PanelChip("0X", "#b3261e")


class EmeraldPresenter:
    def __init__(
        self,
        species_info: dict[str, dict[str, object]],
        item_names: dict[int, str],
        move_info: dict[int, dict[str, object]],
        ability_names: dict[int, str],
        type_chart: tuple[tuple[int, int, int], ...],
        icon_for: Callable[[str], str] | None = None,
    ) -> None:
        self._species_info = species_info
        self._item_names = item_names
        self._move_info = move_info
        self._ability_names = ability_names
        self._type_chart_rows = type_chart
        self._icon_for = icon_for
        self._type_chart = {
            (attack, defense): multiplier / 10
            for attack, defense, multiplier in type_chart
        }

    def icon_path(self, species: str) -> str:
        return self._icon_for(species) if self._icon_for is not None else ""

    def species_types(self, species: str) -> tuple[int, ...]:
        metadata = self._species_info.get(species, {})
        return tuple(int(value) for value in metadata.get("types", ()))

    def party_section(self, party: tuple[PokemonState, ...]) -> PanelSection | None:
        if not party:
            return None
        rows = tuple(
            PanelRow(
                f"{display_constant(member.species, 'SPECIES_')} · Lv {member.level} · "
                f"HP {member.hp}/{member.max_hp}",
                progress=(member.hp / member.max_hp) if member.max_hp else None,
                icon=self.icon_path(member.species),
                chips=status_chips(member.status)
                or tuple(
                    chip
                    for chip in map(type_chip, dict.fromkeys(self.species_types(member.species)))
                    if chip is not None
                ),
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
        in_game_partner: bool = False,
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
                in_game_partner=in_game_partner,
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
                f"HP {member.hp}/{member.max_hp}",
                progress=(member.hp / member.max_hp) if member.max_hp else None,
                icon=self.icon_path(member.species),
                chips=status_chips(member.status),
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
        active_players: tuple[BattlePokemonState, ...] = (),
    ) -> PanelSection | None:
        """Best damage estimate per opponent plus the worst incoming threat.

        Integer Gen III damage math with live stats and stat stages; abilities,
        held items, screens, weather and crits are not modeled.
        """
        rows = []
        for opponent in active_opponents:
            best = None
            for member in party:
                if member.hp <= 0 or member.is_egg:
                    continue
                for move_id in member.moves:
                    move = self._move_info.get(move_id)
                    if not move or int(move.get("power", 0)) <= 0:
                        continue
                    move_type = int(move.get("type", -1))
                    multipliers = type_multipliers(
                        self._type_chart_rows, move_type, opponent.types
                    )
                    attack_stat, burned = attacker_offense(
                        member, active_players, move_type
                    )
                    low, high = damage_range(
                        level=member.level,
                        power=int(move.get("power", 0)),
                        move_type=move_type,
                        attacker_types=self.species_types(member.species),
                        attack_stat=attack_stat,
                        defense_stat=defender_defense(opponent, move_type),
                        multipliers=multipliers,
                        burned=burned,
                    )
                    if high <= 0:
                        continue
                    candidate = (
                        high,
                        low,
                        member,
                        str(move.get("name", f"Move {move_id}")),
                        effectiveness_value(multipliers),
                    )
                    if best is None or candidate[:2] > best[:2]:
                        best = candidate
            if best is None:
                continue
            high, low, member, move_name, effectiveness = best
            low_percent = 100 * low // max(1, opponent.max_hp)
            high_percent = 100 * high // max(1, opponent.max_hp)
            best_hits, worst_hits = hits_to_ko(opponent.hp, low, high)
            if best_hits == 1 and worst_hits == 1:
                ko_note = "KO"
            elif best_hits == worst_hits:
                ko_note = f"{best_hits} hits"
            else:
                ko_note = f"{best_hits}-{worst_hits} hits"
            active_member = active_battle_state(member, active_players)
            member_speed = (
                staged_stat(active_member.stats[2], active_member.stat_stages[3])
                if active_member is not None
                else member.stats[2]
            )
            opponent_speed = staged_stat(
                opponent.stats[2], opponent.stat_stages[3]
            )
            speed_note = ""
            if member_speed and opponent_speed:
                speed_note = (
                    " · likely faster"
                    if member_speed > opponent_speed
                    else " · likely slower"
                )
            rows.append(
                PanelRow(
                    f"{display_constant(member.species, 'SPECIES_')} {move_name} → "
                    f"{display_constant(opponent.species, 'SPECIES_')} · "
                    f"{low_percent}-{high_percent}% · {ko_note}{speed_note}",
                    tooltip=(
                        "Gen III integer damage from live stats and stat stages. "
                        "Abilities, items, screens, weather and crits are not "
                        "included."
                    ),
                    chips=(effectiveness_chip(effectiveness),),
                )
            )

        threat = self._worst_threat(
            enemy_party, party, active_opponents, active_players
        )
        if threat is not None:
            rows.append(threat)
        if not rows:
            return None
        return PanelSection(
            "Battle advice",
            tuple(rows),
            priority=2,
            role="urgent",
            compact_rows=tuple(rows[:2]),
        )

    def _worst_threat(
        self,
        enemy_party: tuple[PokemonState, ...],
        party: tuple[PokemonState, ...],
        active_opponents: tuple[BattlePokemonState, ...],
        active_players: tuple[BattlePokemonState, ...],
    ) -> PanelRow | None:
        worst = None
        for enemy in enemy_party:
            if enemy.hp <= 0:
                continue
            for move_id in enemy.moves:
                move = self._move_info.get(move_id)
                if not move or int(move.get("power", 0)) <= 0:
                    continue
                move_type = int(move.get("type", -1))
                for member in party:
                    if member.hp <= 0 or member.is_egg or not member.max_hp:
                        continue
                    multipliers = type_multipliers(
                        self._type_chart_rows,
                        move_type,
                        tuple(self.species_types(member.species)),
                    )
                    attack_stat, burned = attacker_offense(
                        enemy, active_opponents, move_type
                    )
                    active_member = active_battle_state(member, active_players)
                    defense_stat = (
                        defender_defense(active_member, move_type)
                        if active_member is not None
                        else (
                        member.stats[1]
                        if move_type in PHYSICAL_TYPES
                        else member.stats[4]
                        )
                    )
                    low, high = damage_range(
                        level=enemy.level,
                        power=int(move.get("power", 0)),
                        move_type=move_type,
                        attacker_types=self.species_types(enemy.species),
                        attack_stat=attack_stat,
                        defense_stat=defense_stat,
                        multipliers=multipliers,
                        burned=burned,
                    )
                    if high <= 0:
                        continue
                    fraction = high / member.max_hp
                    candidate = (
                        fraction,
                        low,
                        high,
                        enemy,
                        member,
                        str(move.get("name", f"Move {move_id}")),
                        effectiveness_value(multipliers),
                    )
                    if worst is None or candidate[0] > worst[0]:
                        worst = candidate
        if worst is None:
            return None
        _, low, high, enemy, member, move_name, effectiveness = worst
        low_percent = 100 * low // member.max_hp
        high_percent = 100 * high // member.max_hp
        return PanelRow(
            f"Threat · {display_constant(enemy.species, 'SPECIES_')} {move_name} → "
            f"{display_constant(member.species, 'SPECIES_')} · "
            f"{low_percent}-{high_percent}%",
            emphasis="danger",
            chips=(effectiveness_chip(effectiveness),),
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