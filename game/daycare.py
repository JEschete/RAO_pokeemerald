from dataclasses import dataclass

from retroarch_overlay.core.contracts import MemoryReader
from retroarch_overlay.models import PanelAction, PanelRow, PanelSection

from .state import BoxPokemonState, PokemonState, decode_box_pokemon


DAYCARE_OFFSET = 0x3030
DAYCARE_SIZE = 0x120
DAYCARE_MON_SIZE = 0x8C
DAYCARE_STEPS_OFFSET = 0x88
OFFSPRING_PERSONALITY_OFFSET = 0x118
EGG_STEP_COUNTER_OFFSET = 0x11C
ABILITY_MAGMA_ARMOR = 40
ABILITY_FLAME_BODY = 49


@dataclass(frozen=True, slots=True)
class DepositedPokemon:
    pokemon: BoxPokemonState
    steps: int


def egg_steps_remaining(
    cycles: int, step_counter: int, cycles_per_tick: int
) -> int:
    ticks_to_hatch = (cycles + cycles_per_tick - 1) // cycles_per_tick + 1
    steps_to_next_tick = 256 if step_counter == 255 else 255 - step_counter
    return steps_to_next_tick + (ticks_to_hatch - 1) * 256


class DaycareDashboard:
    def __init__(
        self,
        species_by_id: dict[int, str],
        species_info: dict[str, dict[str, object]],
        flag_ids: dict[str, int],
    ) -> None:
        self._species_by_id = species_by_id
        self._species_info = species_info
        self._flag_ids = flag_ids

    def section(
        self,
        memory: MemoryReader,
        save_block_1: int,
        flags: bytes,
        party: tuple[PokemonState, ...],
    ) -> PanelSection:
        data = memory.read_memory(save_block_1 + DAYCARE_OFFSET, DAYCARE_SIZE)
        if len(data) != DAYCARE_SIZE:
            raise ValueError(
                f"Expected {DAYCARE_SIZE} daycare bytes, received {len(data)}"
            )
        deposited = []
        for index in range(2):
            offset = index * DAYCARE_MON_SIZE
            pokemon = decode_box_pokemon(
                data[offset : offset + 0x50], self._species_by_id
            )
            if pokemon is not None:
                deposited.append(
                    DepositedPokemon(
                        pokemon,
                        int.from_bytes(
                            data[
                                offset + DAYCARE_STEPS_OFFSET :
                                offset + DAYCARE_STEPS_OFFSET + 4
                            ],
                            "little",
                        ),
                    )
                )
        pending = bool(
            int.from_bytes(
                data[OFFSPRING_PERSONALITY_OFFSET : OFFSPRING_PERSONALITY_OFFSET + 4],
                "little",
            )
        ) or self._flag(flags, "FLAG_PENDING_DAYCARE_EGG")
        compatibility = (
            self._compatibility(deposited[0].pokemon, deposited[1].pokemon)
            if len(deposited) == 2
            else 0
        )
        eggs = [member for member in party if member.is_egg]
        rows = (
            PanelRow(
                f"Deposited {len(deposited)}/2 · "
                f"{'Egg ready' if pending else self._compatibility_label(compatibility)}"
            ),
            PanelRow(f"Party eggs {len(eggs)}"),
        )
        details = [PanelRow("DAYCARE")]
        if not deposited:
            details.append(PanelRow("No Pokémon deposited"))
        for entry in deposited:
            current_level = self._level_for_experience(
                entry.pokemon.species,
                entry.pokemon.experience + entry.steps,
            )
            details.append(
                PanelRow(
                    f"{self._name(entry.pokemon.species)} · Lv {current_level} · "
                    f"{entry.steps} EXP gained"
                )
            )
        if len(deposited) == 2:
            details.append(
                PanelRow(
                    f"Compatibility · {compatibility}% · "
                    f"{self._compatibility_label(compatibility)}"
                )
            )
        details.append(PanelRow(f"Pending egg · {'YES' if pending else 'no'}"))
        if eggs:
            details.append(PanelRow("PARTY EGGS"))
            step_counter = data[EGG_STEP_COUNTER_OFFSET]
            subtract = 2 if self._has_hatch_ability(party) else 1
            for egg in eggs:
                steps = egg_steps_remaining(
                    egg.friendship, step_counter, subtract
                )
                details.append(
                    PanelRow(
                        f"Slot {egg.slot + 1} · {egg.friendship} cycle(s) · "
                        f"≤{steps} steps"
                        f" · {'Flame Body/Magma Armor' if subtract == 2 else 'normal rate'}"
                    )
                )
        return PanelSection(
            "Daycare & eggs",
            rows,
            actions=(PanelAction("OPEN DAYCARE", "Daycare and Breeding", tuple(details)),),
            priority=35,
            role="goals",
            compact_rows=(rows[0],),
        )

    def _compatibility(self, first: BoxPokemonState, second: BoxPokemonState) -> int:
        first_info = self._species_info[first.species]
        second_info = self._species_info[second.species]
        first_groups = tuple(first_info.get("egg_groups", ()))
        second_groups = tuple(second_info.get("egg_groups", ()))
        if not first_groups or not second_groups or 15 in first_groups or 15 in second_groups:
            return 0
        if 13 in first_groups and 13 in second_groups:
            return 0
        if 13 in first_groups or 13 in second_groups:
            return 20 if first.ot_id == second.ot_id else 50
        first_gender = self._gender(first, int(first_info.get("gender_ratio", 255)))
        second_gender = self._gender(second, int(second_info.get("gender_ratio", 255)))
        if first_gender == second_gender or "genderless" in {first_gender, second_gender}:
            return 0
        if not set(first_groups) & set(second_groups):
            return 0
        if first.species_id == second.species_id:
            return 50 if first.ot_id == second.ot_id else 70
        return 50 if first.ot_id != second.ot_id else 20

    @staticmethod
    def _gender(pokemon: BoxPokemonState, ratio: int) -> str:
        if ratio == 255:
            return "genderless"
        if ratio == 254:
            return "female"
        if ratio == 0:
            return "male"
        return "female" if pokemon.personality & 0xFF < ratio else "male"

    def _level_for_experience(self, species: str, experience: int) -> int:
        growth = str(self._species_info[species]["growth_rate"])
        level = 1
        while level < 100 and _experience_for_level(growth, level + 1) <= experience:
            level += 1
        return level

    def _has_hatch_ability(self, party: tuple[PokemonState, ...]) -> bool:
        for member in party:
            if member.is_egg:
                continue
            abilities = self._species_info.get(member.species, {}).get("abilities", (0, 0))
            ability = int(abilities[min(member.ability_slot, len(abilities) - 1)])
            if ability in {ABILITY_MAGMA_ARMOR, ABILITY_FLAME_BODY}:
                return True
        return False

    def _flag(self, flags: bytes, name: str) -> bool:
        flag_id = self._flag_ids.get(name)
        return flag_id is not None and flag_id // 8 < len(flags) and bool(flags[flag_id // 8] & (1 << (flag_id % 8)))

    @staticmethod
    def _compatibility_label(value: int) -> str:
        return {0: "Incompatible", 20: "Low", 50: "Medium", 70: "High"}.get(value, "Unknown")

    @staticmethod
    def _name(species: str) -> str:
        return " ".join(word.capitalize() for word in species.removeprefix("SPECIES_").split("_"))


def _experience_for_level(growth: str, level: int) -> int:
    if level <= 1:
        return level
    if growth == "GROWTH_FAST":
        return 4 * level**3 // 5
    if growth == "GROWTH_MEDIUM_FAST":
        return level**3
    if growth == "GROWTH_MEDIUM_SLOW":
        return 6 * level**3 // 5 - 15 * level**2 + 100 * level - 140
    if growth == "GROWTH_SLOW":
        return 5 * level**3 // 4
    if growth == "GROWTH_ERRATIC":
        if level <= 50:
            return (100 - level) * level**3 // 50
        if level <= 68:
            return (150 - level) * level**3 // 100
        if level <= 98:
            return ((1911 - 10 * level) // 3) * level**3 // 500
        return (160 - level) * level**3 // 100
    if level <= 15:
        return ((level + 1) // 3 + 24) * level**3 // 50
    if level <= 36:
        return (level + 14) * level**3 // 50
    return (level // 2 + 32) * level**3 // 50