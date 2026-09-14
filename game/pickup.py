"""Pickup ability monitoring.

Watches party members whose active Gen III ability is Pickup and reports when
one is suddenly holding an item it did not have before — the free item is
easy to miss and silently blocks further pickups until collected.
"""

from retroarch_overlay.models import PanelRow, PanelSection

from .state import PokemonState

ABILITY_PICKUP = 53


def _display(species: str) -> str:
    return " ".join(
        word.capitalize() for word in species.removeprefix("SPECIES_").split("_")
    )


class PickupWatcher:
    def __init__(
        self,
        species_info: dict[str, dict[str, object]],
        item_names: dict[int, str],
    ) -> None:
        self._species_info = species_info
        self._item_names = item_names
        self._identity = ""
        self._held: dict[int, int] = {}

    def reset_session(self) -> None:
        self._identity = ""
        self._held = {}

    def has_pickup(self, member: PokemonState) -> bool:
        metadata = self._species_info.get(member.species, {})
        abilities = metadata.get("abilities", [0, 0])
        slot = min(member.ability_slot, len(abilities) - 1)
        return int(abilities[slot]) == ABILITY_PICKUP

    def observe(
        self, identity: str, party: tuple[PokemonState, ...]
    ) -> list[str]:
        """Journal-ready texts for freshly picked-up items."""
        holders = {
            member.personality: member.held_item_id
            for member in party
            if self.has_pickup(member) and not member.is_egg
        }
        if identity != self._identity:
            self._identity = identity
            self._held = holders
            return []
        events = []
        for member in party:
            if member.personality not in holders:
                continue
            previous = self._held.get(member.personality)
            if previous == 0 and member.held_item_id:
                item = self._item_names.get(
                    member.held_item_id, f"item {member.held_item_id}"
                )
                events.append(f"{_display(member.species)} picked up {item}")
        if party:
            self._held = holders
        return events

    def section(self, party: tuple[PokemonState, ...]) -> PanelSection | None:
        holders = [
            member
            for member in party
            if self.has_pickup(member) and not member.is_egg
        ]
        if not holders:
            return None
        rows = []
        ready = 0
        for member in holders:
            if member.held_item_id:
                item = self._item_names.get(
                    member.held_item_id, f"Item {member.held_item_id}"
                )
                ready += 1
                rows.append(
                    PanelRow(
                        f"{_display(member.species)} · holding {item}",
                        emphasis="success",
                    )
                )
            else:
                rows.append(
                    PanelRow(f"{_display(member.species)} · empty-handed")
                )
        return PanelSection(
            f"Pickup · {ready} to collect" if ready else "Pickup",
            tuple(rows),
            priority=30 if ready else 60,
            role="party",
            compact_rows=(PanelRow(f"{ready}/{len(holders)} holding items"),),
            key="pickup",
        )
