"""Wild Pokémon IV readout with an upgrade verdict.

The wild battler's IVs are read directly from battle memory. The verdict
compares its IV total against the best party member in the same evolution
family (family membership comes from the pinned decomp's evolution edges),
so a wild Ralts is measured against your Gardevoir.
"""

from retroarch_overlay.models import PanelChip, PanelRow, PanelSection

from .state import BattlePokemonState, PokemonState, NATURE_NAMES, STAT_NAMES


def build_family_map(
    evolutions: dict[str, list[dict[str, str]]]
) -> dict[str, str]:
    """Species → stable family identifier via union-find over evolution edges."""
    parent: dict[str, str] = {}

    def find(species: str) -> str:
        parent.setdefault(species, species)
        while parent[species] != species:
            parent[species] = parent[parent[species]]
            species = parent[species]
        return species

    def union(first: str, second: str) -> None:
        root_first, root_second = find(first), find(second)
        if root_first != root_second:
            parent[root_second] = root_first

    for species, edges in evolutions.items():
        for edge in edges:
            target = edge.get("target")
            if target:
                union(species, target)
    # Canonicalize every component to its lexicographically first member so
    # the identifier does not depend on iteration order.
    members: dict[str, list[str]] = {}
    for species in parent:
        members.setdefault(find(species), []).append(species)
    canonical = {}
    for group in members.values():
        family = min(group)
        for species in group:
            canonical[species] = family
    return canonical


def _display(species: str) -> str:
    return " ".join(
        word.capitalize() for word in species.removeprefix("SPECIES_").split("_")
    )


class WildScout:
    def __init__(self, family_map: dict[str, str]) -> None:
        self._family_map = family_map

    def family_of(self, species: str) -> str:
        return self._family_map.get(species, species)

    def section(
        self,
        opponent: BattlePokemonState,
        party: tuple[PokemonState, ...],
    ) -> PanelSection | None:
        ivs = opponent.ivs
        total = sum(ivs)
        nature = NATURE_NAMES[opponent.personality % len(NATURE_NAMES)]
        rows = [
            PanelRow(
                " · ".join(
                    f"{name} {value}" for name, value in zip(STAT_NAMES, ivs)
                ),
                tooltip="Individual values read from battle memory (0-31 each).",
            ),
            PanelRow(
                f"IV total {total}/186 · {nature}",
                progress=total / 186,
                progress_color="accent",
            ),
        ]
        rows.append(self._verdict_row(opponent, party, total))
        return PanelSection(
            f"Wild IVs · {_display(opponent.species)}",
            tuple(rows),
            priority=7,
            role="urgent",
            compact_rows=(rows[1],),
        )

    def _verdict_row(
        self,
        opponent: BattlePokemonState,
        party: tuple[PokemonState, ...],
        total: int,
    ) -> PanelRow:
        family = self.family_of(opponent.species)
        best = None
        for member in party:
            if member.is_egg or self.family_of(member.species) != family:
                continue
            member_total = sum(member.ivs)
            if best is None or member_total > best[0]:
                best = (member_total, member)
        if best is None:
            return PanelRow(
                "No party member in this evolution line",
                emphasis="muted",
            )
        best_total, member = best
        difference = total - best_total
        if difference > 0:
            return PanelRow(
                f"Better than your {_display(member.species)} ({best_total})",
                emphasis="success",
                chips=(PanelChip(f"UPGRADE +{difference}", "#27824a"),),
            )
        return PanelRow(
            f"Your {_display(member.species)} is better ({best_total})",
            emphasis="muted",
            chips=(PanelChip(f"{difference} IVs", "#687064"),),
        )
