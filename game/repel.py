"""Repel planning against the current map's encounter tables.

Gen III blocks a wild encounter after slot selection when the selected
Pokémon's level is below the first party member's level, so a repel thins
encounters without renormalizing the surviving species' slot odds.
"""

from typing import Any

from retroarch_overlay.models import PanelRow, PanelSection

from .state import PokemonState


def repel_lead(party: tuple[PokemonState, ...]) -> PokemonState | None:
    for member in party:
        if not member.is_egg:
            return member
    return None


def surviving_species(
    field_definition: dict[str, Any],
    encounter_field: dict[str, Any],
    lead_level: int,
) -> tuple[dict[str, dict[str, int]], int, int]:
    """Species that can still appear under a repel, plus blocked slot odds.

    Returns (surviving, blocked_percent, total_percent); surviving maps
    species to effective min/max levels and their unchanged slot chance.
    """
    rates = field_definition["encounter_rates"]
    surviving: dict[str, dict[str, int]] = {}
    blocked_percent = 0
    total_percent = 0
    for rate, mon in zip(rates, encounter_field["mons"]):
        total_percent += rate
        if mon["max_level"] < lead_level:
            blocked_percent += rate
            continue
        entry = surviving.setdefault(
            mon["species"],
            {
                "min": max(mon["min_level"], lead_level),
                "max": mon["max_level"],
                "chance": 0,
            },
        )
        entry["min"] = min(entry["min"], max(mon["min_level"], lead_level))
        entry["max"] = max(entry["max"], mon["max_level"])
        entry["chance"] += rate
    return surviving, blocked_percent, total_percent


def repel_section(
    field_definitions: dict[str, dict[str, Any]],
    encounter: dict[str, Any],
    party: tuple[PokemonState, ...],
    repel_steps: int,
    display: Any,
) -> PanelSection | None:
    lead = repel_lead(party)
    if lead is None:
        return None
    methods = (
        ("land_mons", "Land"),
        ("water_mons", "Water"),
    )
    if not any(field_name in encounter for field_name, _ in methods):
        return None
    if repel_steps:
        status = f"Repel active · {repel_steps} steps · lead Lv {lead.level}"
    else:
        status = f"No repel · lead Lv {lead.level} would block:"
    rows = [PanelRow(status, emphasis="success" if repel_steps else "")]
    for field_name, title in methods:
        field = encounter.get(field_name)
        if field is None:
            continue
        surviving, blocked, total = surviving_species(
            field_definitions[field_name], field, lead.level
        )
        if not total:
            continue
        if not surviving:
            rows.append(PanelRow(f"{title}: every species blocked", emphasis="muted"))
            continue
        rows.append(
            PanelRow(
                f"{title}: blocks {blocked * 100 // total}% of encounters",
                emphasis="muted",
            )
        )
        for species, values in sorted(
            surviving.items(), key=lambda item: -item[1]["chance"]
        ):
            level_text = (
                f"Lv {values['min']}"
                if values["min"] == values["max"]
                else f"Lv {values['min']}-{values['max']}"
            )
            rows.append(
                PanelRow(
                    f"{display(species, 'SPECIES_')} · {level_text} · "
                    f"{values['chance']}%"
                )
            )
    if len(rows) <= 1:
        return None
    return PanelSection(
        "Repel planner",
        tuple(rows),
        preview_limit=4,
        priority=16 if repel_steps else 34,
        role="area",
        compact_rows=(rows[0],),
    )
