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
        if member.hp > 0 and not member.is_egg:
            return member
    return None


def surviving_species(
    field_definition: dict[str, Any],
    encounter_field: dict[str, Any],
    lead_level: int,
) -> tuple[dict[str, dict[str, int]], int, int]:
    """Species that can still appear under a repel, plus blocked odds.

    Returns (surviving, blocked_percent, total_percent); surviving maps
    species to effective min/max levels and their post-Repel chance.
    """
    rates = field_definition["encounter_rates"]
    surviving: dict[str, dict[str, int]] = {}
    blocked_percent = 0.0
    total_percent = 0.0
    for rate, mon in zip(rates, encounter_field["mons"]):
        total_percent += rate
        minimum = min(mon["min_level"], mon["max_level"])
        maximum = max(mon["min_level"], mon["max_level"])
        surviving_minimum = max(minimum, lead_level)
        level_count = maximum - minimum + 1
        surviving_count = max(0, maximum - surviving_minimum + 1)
        chance = rate * surviving_count / level_count
        blocked_percent += rate - chance
        if not surviving_count:
            continue
        entry = surviving.setdefault(
            mon["species"],
            {
                "min": surviving_minimum,
                "max": maximum,
                "chance": 0,
            },
        )
        entry["min"] = min(entry["min"], surviving_minimum)
        entry["max"] = max(entry["max"], maximum)
        entry["chance"] += chance
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
        ("rock_smash_mons", "Rock Smash"),
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
                f"{title}: blocks {blocked * 100 / total:.1f}% of encounters",
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
                    f"{values['chance']:.1f}%"
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
