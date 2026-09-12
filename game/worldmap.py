"""Hoenn region-map view: one hoverable marker per map section.

Aggregates everything still outstanding in a section - items on the ground,
trainers not yet battled, and species not yet registered - so the region map
answers "where do I still have things to do".
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from retroarch_overlay.models import MapWaypoint

from .mapdata import (
    KIND_HIDDEN,
    KIND_ITEM,
    KIND_REMATCH,
    KIND_TRAINER,
    EmeraldMapEntry,
    display_name,
)
from .mapoverlays import flag_is_set


REGION_COLS = 32
REGION_ROWS = 20
REGION_TILE = 8
KIND_REGION = "regions"

# The 28x15 section layout sits at this tile offset inside the 32x20 map image
# (MAPCURSOR_X_MIN / MAPCURSOR_Y_MIN in region_map.c).
REGION_ORIGIN_X = 1
REGION_ORIGIN_Y = 2
LAYOUT_COLS = 28
LAYOUT_ROWS = 15
SECTION_PATTERN = re.compile(r"MAPSEC_[A-Z0-9_]+")

ENCOUNTER_METHODS = (
    ("land_mons", "Grass", None),
    ("water_mons", "Surf", None),
    ("rock_smash_mons", "Rock Smash", None),
    ("fishing_mons", "Old Rod", "old_rod"),
    ("fishing_mons", "Good Rod", "good_rod"),
    ("fishing_mons", "Super Rod", "super_rod"),
)


@dataclass(frozen=True, slots=True)
class RegionSection:
    section_id: str
    name: str
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


def load_region_sections(root: Path) -> dict[str, RegionSection]:
    path = root / "src" / "data" / "region_map" / "region_map_sections.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    sections = {}
    for raw in document.get("map_sections", ()):
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        sections[raw["id"]] = RegionSection(
            raw["id"],
            str(raw.get("name", raw["id"])).title(),
            int(raw.get("x", 0)),
            int(raw.get("y", 0)),
            max(1, int(raw.get("width", 1))),
            max(1, int(raw.get("height", 1))),
        )
    return sections


def parse_region_layout(root: Path) -> tuple[tuple[str, ...], ...]:
    """The 28x15 grid naming which section owns each region-map cell."""
    path = root / "src" / "data" / "region_map" / "region_map_layout.h"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("{MAPSEC"):
            continue
        found = SECTION_PATTERN.findall(line)
        if len(found) == LAYOUT_COLS:
            rows.append(tuple(found))
    if len(rows) != LAYOUT_ROWS:
        raise ValueError(
            f"Region map layout should have {LAYOUT_ROWS} rows, found {len(rows)}"
        )
    return tuple(rows)


def section_positions(
    layout: tuple[tuple[str, ...], ...],
    sections: dict[str, RegionSection],
) -> dict[str, tuple[int, int]]:
    """Image-tile position for each section that is actually on the map.

    Anchors on a cell the section really owns, so an L-shaped route never puts
    its marker on a neighbour's tile.
    """
    cells: dict[str, list[tuple[int, int]]] = {}
    for row_index, row in enumerate(layout):
        for column, section_id in enumerate(row):
            if section_id != "MAPSEC_NONE":
                cells.setdefault(section_id, []).append((column, row_index))
    positions = {}
    for section_id, owned in cells.items():
        section = sections.get(section_id)
        chosen = None
        if section is not None:
            candidate = (
                section.x + section.width // 2,
                section.y + section.height // 2,
            )
            if candidate in owned:
                chosen = candidate
        if chosen is None:
            chosen = sorted(owned)[len(owned) // 2]
        positions[section_id] = (
            chosen[0] + REGION_ORIGIN_X,
            chosen[1] + REGION_ORIGIN_Y,
        )
    return positions


def uncaught_species(
    encounter: dict,
    field_definitions: dict,
    encounter_species,
    is_caught,
    caught_flags: bytes,
) -> list[str]:
    """Species still missing from the dex here, labelled by how to meet them."""
    lines = []
    for field_name, label, group in ENCOUNTER_METHODS:
        if field_name not in encounter:
            continue
        indexes = None
        if group is not None:
            groups = field_definitions.get(field_name, {}).get("groups", {})
            indexes = groups.get(group)
            if not indexes:
                continue
        species = encounter_species(field_name, encounter[field_name], indexes)
        missing = [
            display_name(name, "SPECIES_")
            for name in species
            if not is_caught(name, caught_flags)
        ]
        if missing:
            lines.append(f"{label}: {', '.join(sorted(set(missing)))}")
    return lines


def world_waypoints(
    sections: dict[str, RegionSection],
    grouped: dict[str, list[EmeraldMapEntry]],
    flags: bytes,
    caught_flags: bytes,
    encounters: dict,
    field_definitions: dict,
    encounter_species,
    is_caught,
    positions: dict[str, tuple[int, int]] | None = None,
    parents: dict[str, str] | None = None,
) -> tuple[MapWaypoint, ...]:
    positions = positions or {}
    parents = parents or {}
    merged: dict[str, list[EmeraldMapEntry]] = {}
    for section_id, entries in grouped.items():
        target = parents.get(section_id, section_id)
        if positions and target not in positions:
            continue
        merged.setdefault(target, []).extend(entries)
    waypoints = []
    for section_id, entries in sorted(merged.items()):
        section = sections.get(section_id)
        if section is None:
            continue
        items = trainers = 0
        for entry in entries:
            for marker in entry.markers:
                if marker.flag is None or flag_is_set(flags, marker.flag):
                    continue
                if marker.kind in {KIND_ITEM, KIND_HIDDEN}:
                    items += 1
                elif marker.kind in {KIND_TRAINER, KIND_REMATCH}:
                    trainers += 1
        missing: list[str] = []
        for entry in entries:
            encounter = encounters.get(entry.map_id)
            if encounter is None:
                continue
            missing.extend(
                uncaught_species(
                    encounter,
                    field_definitions,
                    encounter_species,
                    is_caught,
                    caught_flags,
                )
            )
        detail = []
        if items:
            detail.append(f"{items} item{'s' if items != 1 else ''} left to collect")
        if trainers:
            detail.append(
                f"{trainers} trainer{'s' if trainers != 1 else ''} left to battle"
            )
        if missing:
            detail.append("Not yet caught -")
            detail.extend(f"  {line}" for line in dict.fromkeys(missing))
        if not detail:
            detail.append("Nothing left here")
        x, y = positions.get(section_id, section.center)
        waypoints.append(
            MapWaypoint(
                x,
                y,
                section.name,
                "\n".join(detail),
                KIND_REGION,
                not (items or trainers or missing),
                "quest" if (items or trainers or missing) else "person",
            )
        )
    return tuple(waypoints)
