"""Battle Factory rental inspection and swap advice.

The save keeps six RentalMon records: slots 0-2 are the player's current
rentals and slots 3-5 the beaten opponent's Pokémon offered on the swap
screen. Everything shown here is decoded from those records plus the pinned
decomp's gBattleFrontierMons table — no facility RNG is predicted.
"""

from dataclasses import dataclass
from typing import Any

from retroarch_overlay.models import PanelChip, PanelRow

from .state import NATURE_NAMES

# Offsets relative to the frontier block read (SaveBlock2 + 0x64C).
RENTALS_OFFSET = 0x824
RENTAL_SIZE = 12
RENTAL_COUNT = 6
PLAYER_RENTALS = 3


@dataclass(frozen=True, slots=True)
class RentalMon:
    mon_id: int
    personality: int
    ivs: int
    ability_slot: int


def decode_rentals(frontier_data: bytes) -> tuple[RentalMon, ...]:
    rentals = []
    for index in range(RENTAL_COUNT):
        offset = RENTALS_OFFSET + index * RENTAL_SIZE
        record = frontier_data[offset : offset + RENTAL_SIZE]
        if len(record) < RENTAL_SIZE:
            break
        rentals.append(
            RentalMon(
                mon_id=int.from_bytes(record[0:2], "little"),
                personality=int.from_bytes(record[4:8], "little"),
                ivs=record[8],
                ability_slot=record[9],
            )
        )
    return tuple(rentals)


def _display(species: str) -> str:
    return " ".join(
        word.capitalize() for word in species.removeprefix("SPECIES_").split("_")
    )


class FactoryAdvisor:
    def __init__(
        self,
        frontier_mons: list[dict[str, Any]],
        species_info: dict[str, dict[str, Any]],
        move_info: dict[int, dict[str, Any]],
        item_names: dict[int, str],
        type_chart: tuple[tuple[int, int, int], ...],
    ) -> None:
        self._frontier_mons = frontier_mons
        self._species_info = species_info
        self._move_info = move_info
        self._item_names = item_names
        self._chart = {
            (attack, defense): multiplier
            for attack, defense, multiplier in type_chart
        }
        self._all_types = sorted(
            {defense for _, defense, _ in type_chart}
        )

    def entry(self, rental: RentalMon) -> dict[str, Any] | None:
        if not 0 < rental.mon_id < len(self._frontier_mons):
            return None
        entry = self._frontier_mons[rental.mon_id]
        return entry if entry.get("species") else None

    def rental_rows(self, rentals: tuple[RentalMon, ...]) -> list[PanelRow]:
        """Detail rows for the player's current rental team."""
        rows: list[PanelRow] = []
        for rental in rentals[:PLAYER_RENTALS]:
            entry = self.entry(rental)
            if entry is None:
                continue
            species = str(entry["species"])
            nature = NATURE_NAMES[int(entry["nature"]) % len(NATURE_NAMES)]
            item = self._item_names.get(int(entry["item"]), "No item")
            rows.append(
                PanelRow(
                    f"{_display(species)} · {nature} · {item} · IVs {rental.ivs}",
                    emphasis="heading",
                )
            )
            moves = ", ".join(
                str(self._move_info.get(move, {}).get("name", f"Move {move}"))
                for move in entry["moves"]
                if move
            )
            rows.append(PanelRow(moves))
        return rows

    def swap_rows(self, rentals: tuple[RentalMon, ...]) -> list[PanelRow]:
        """Swap-screen advice: coverage delta for taking each candidate."""
        team = [
            entry
            for rental in rentals[:PLAYER_RENTALS]
            if (entry := self.entry(rental)) is not None
        ]
        candidates = [
            entry
            for rental in rentals[PLAYER_RENTALS:]
            if (entry := self.entry(rental)) is not None
        ]
        if len(team) < PLAYER_RENTALS or not candidates:
            return []
        base = self.team_score(team)
        best: tuple[int, int, int] | None = None  # (delta, slot, candidate idx)
        for candidate_index, candidate in enumerate(candidates):
            for slot in range(len(team)):
                trial = list(team)
                trial[slot] = candidate
                delta = self.team_score(trial) - base
                if best is None or delta > best[0]:
                    best = (delta, slot, candidate_index)
        if best is None:
            return []
        delta, slot, candidate_index = best
        keep = PanelRow(
            "Swap advice: keep your current team",
            emphasis="muted",
            tooltip=(
                "Score = types your team hits super-effectively minus types "
                "that are super-effective against two or more of your rentals."
            ),
        )
        if delta <= 0:
            return [keep]
        out = str(team[slot]["species"])
        into = str(candidates[candidate_index]["species"])
        return [
            PanelRow(
                f"Swap {_display(out)} → {_display(into)}",
                emphasis="success",
                chips=(PanelChip(f"+{delta} score", "#27824a"),),
                tooltip=(
                    "Score = types your team hits super-effectively minus "
                    "types that are super-effective against two or more of "
                    "your rentals. Abilities are not modeled."
                ),
            )
        ]

    def team_score(self, team: list[dict[str, Any]]) -> int:
        """Offensive coverage minus shared defensive weaknesses."""
        covered = set()
        weaknesses: dict[int, int] = {}
        for entry in team:
            move_types = {
                int(self._move_info.get(move, {}).get("type", -1))
                for move in entry["moves"]
                if move
                and int(self._move_info.get(move, {}).get("power", 0)) > 0
            }
            for defense in self._all_types:
                if any(
                    self._chart.get((move_type, defense), 10) >= 20
                    for move_type in move_types
                ):
                    covered.add(defense)
            species_types = tuple(
                int(value)
                for value in self._species_info.get(
                    str(entry["species"]), {}
                ).get("types", ())
            )
            for attack in self._all_types:
                multiplier = 10
                for defense in dict.fromkeys(species_types):
                    multiplier = multiplier * self._chart.get(
                        (attack, defense), 10
                    ) // 10
                if multiplier > 10:
                    weaknesses[attack] = weaknesses.get(attack, 0) + 1
        shared = sum(1 for count in weaknesses.values() if count >= 2)
        return len(covered) - shared
