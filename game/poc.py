import re
from dataclasses import dataclass
from typing import Any

from retroarch_overlay.models import PanelRow


@dataclass(frozen=True, slots=True)
class PocGate:
    badge: int
    leader: str
    target: int


POC_GATES = (
    PocGate(0, "Roxanne", 39),
    PocGate(2, "Wattson", 66),
    PocGate(3, "Flannery", 90),
    PocGate(1, "Brawly", 101),
    PocGate(4, "Norman", 101),
    PocGate(6, "Tate & Liza", 156),
    PocGate(7, "Juan", 167),
    PocGate(5, "Winona", 171),
)
FINAL_TARGET = 212
STARTER_FAMILIES = (
    ("SPECIES_TREECKO", "SPECIES_GROVYLE", "SPECIES_SCEPTILE"),
    ("SPECIES_TORCHIC", "SPECIES_COMBUSKEN", "SPECIES_BLAZIKEN"),
    ("SPECIES_MUDKIP", "SPECIES_MARSHTOMP", "SPECIES_SWAMPERT"),
)
ROOT_FOSSIL_FAMILY = frozenset(("SPECIES_LILEEP", "SPECIES_CRADILY"))
CLAW_FOSSIL_FAMILY = frozenset(("SPECIES_ANORITH", "SPECIES_ARMALDO"))


@dataclass(frozen=True, slots=True)
class AcquisitionSource:
    species: str
    stage: int
    method: str
    location: str


class PocPlanner:
    def __init__(self, knowledge: dict[str, Any], national_dex: dict[str, int]) -> None:
        self._national_dex = national_dex
        self._flag_ids = {
            name: int(value) for name, value in knowledge["flag_ids"].items()
        }
        self._sources = self._build_sources(knowledge)

    def caught_count(self, caught_flags: bytes, event_flags: bytes) -> int:
        return sum(
            self._is_caught(species, caught_flags)
            for species in self.eligible_species(caught_flags, event_flags)
        )

    def eligible_species(
        self, caught_flags: bytes, event_flags: bytes
    ) -> frozenset[str]:
        eligible = set(self._sources)
        starter = next(
            (
                family
                for family in STARTER_FAMILIES
                if any(self._is_caught(species, caught_flags) for species in family)
            ),
            (),
        )
        eligible.update(starter)
        root_selected = self._named_flag(event_flags, "FLAG_CHOSE_ROOT_FOSSIL")
        claw_selected = self._named_flag(event_flags, "FLAG_CHOSE_CLAW_FOSSIL")
        if not root_selected and not claw_selected:
            root_selected = any(
                self._is_caught(species, caught_flags)
                for species in ROOT_FOSSIL_FAMILY
            )
            claw_selected = any(
                self._is_caught(species, caught_flags)
                for species in CLAW_FOSSIL_FAMILY
            )
        if root_selected:
            eligible.difference_update(CLAW_FOSSIL_FAMILY)
        elif claw_selected:
            eligible.difference_update(ROOT_FOSSIL_FAMILY)
        else:
            eligible.difference_update(ROOT_FOSSIL_FAMILY | CLAW_FOSSIL_FAMILY)
        return frozenset(eligible)

    def rows(
        self,
        caught_flags: bytes,
        event_flags: bytes,
        current_map: str,
        flag_is_set: Any,
    ) -> tuple[PanelRow, ...]:
        gate_index = next(
            (
                index
                for index, gate in enumerate(POC_GATES)
                if not flag_is_set(event_flags, 0x867 + gate.badge)
            ),
            len(POC_GATES),
        )
        gate = POC_GATES[gate_index] if gate_index < len(POC_GATES) else None
        rows = [PanelRow("RA GATE ORDER · GENERATED ACQUISITION GUIDANCE")]
        if gate is None:
            rows.append(PanelRow(f"Final target · {FINAL_TARGET} caught"))
        else:
            rows.append(PanelRow(f"Before {gate.leader} · target {gate.target}"))
        available = []
        later = []
        eligible = self.eligible_species(caught_flags, event_flags)
        selected_starter = next(
            (
                family
                for family in STARTER_FAMILIES
                if any(species in eligible for species in family)
            ),
            (),
        )
        source_index = dict(self._sources)
        for index, species in enumerate(selected_starter):
            source_index.setdefault(
                species,
                (
                    AcquisitionSource(
                        species,
                        0 if index < 2 else 4,
                        "Starter evolution",
                        "LittlerootTown",
                    ),
                ),
            )
        for species in eligible:
            sources = source_index.get(species)
            if not sources:
                continue
            if self._is_caught(species, caught_flags):
                continue
            best = min(
                sources,
                key=lambda source: (
                    source.location != current_map,
                    source.stage,
                    source.method,
                    source.location,
                ),
            )
            (available if best.stage <= gate_index else later).append(best)
        available.sort(
            key=lambda source: (
                source.location != current_map,
                source.stage,
                self._national_dex.get(source.species, 9999),
            )
        )
        later.sort(key=lambda source: (source.stage, self._national_dex.get(source.species, 9999)))
        rows.append(PanelRow(f"AVAILABLE BY THIS GATE · {len(available)} MISSING"))
        rows.extend(self._row(source) for source in available[:80])
        if len(available) > 80:
            rows.append(PanelRow(f"...and {len(available) - 80} more available species"))
        if later:
            rows.append(PanelRow("LATER SOURCES"))
            rows.extend(self._row(source) for source in later[:20])
        return tuple(rows)

    def _named_flag(self, flags: bytes, name: str) -> bool:
        flag_id = self._flag_ids.get(name)
        return (
            flag_id is not None
            and flag_id // 8 < len(flags)
            and bool(flags[flag_id // 8] & (1 << (flag_id % 8)))
        )

    def _is_caught(self, species: str, caught_flags: bytes) -> bool:
        number = self._national_dex.get(species)
        if number is None or number <= 0:
            return False
        bit = number - 1
        return bit // 8 < len(caught_flags) and bool(caught_flags[bit // 8] & (1 << (bit % 8)))

    @staticmethod
    def _row(source: AcquisitionSource) -> PanelRow:
        species = " ".join(
            word.capitalize() for word in source.species.removeprefix("SPECIES_").split("_")
        )
        location = source.location.removeprefix("MAP_").replace("_", " ").title()
        return PanelRow(f"{species} · {source.method} · {location}", False)

    @staticmethod
    def _build_sources(knowledge: dict[str, Any]) -> dict[str, tuple[AcquisitionSource, ...]]:
        sources: dict[str, list[AcquisitionSource]] = {}
        group = knowledge["encounter_group"]
        field_names = {field["type"] for field in group["fields"]}
        for encounter in group["encounters"]:
            map_name = str(encounter["map"])
            stage = map_stage(map_name)
            for field_name in field_names:
                field = encounter.get(field_name)
                if not isinstance(field, dict):
                    continue
                method = field_name.replace("_mons", "").replace("_", " ").title()
                for mon in field.get("mons", ()):
                    source = AcquisitionSource(str(mon["species"]), stage, method, map_name)
                    sources.setdefault(source.species, []).append(source)
        excluded_maps = ("BIRTH_ISLAND", "FARAWAY_ISLAND", "NAVEL_ROCK", "SOUTHERN_ISLAND")
        for species, entries in knowledge["static_acquisitions"].items():
            for entry in entries:
                map_name = str(entry["map"])
                if any(value in map_name.upper() for value in excluded_maps):
                    continue
                sources.setdefault(species, []).append(
                    AcquisitionSource(
                        species,
                        map_stage(map_name),
                        str(entry["kind"]).title(),
                        map_name,
                    )
                )
        changed = True
        while changed:
            changed = False
            for species, evolutions in knowledge["evolutions"].items():
                parents = sources.get(species, ())
                if not parents:
                    continue
                for evolution in evolutions:
                    if str(evolution["method"]).startswith("EVO_TRADE"):
                        continue
                    target = str(evolution["target"])
                    best = min(parents, key=lambda source: source.stage)
                    candidate = AcquisitionSource(
                        target,
                        best.stage,
                        f"Evolve {PocPlanner._species_name(species)}",
                        best.location,
                    )
                    if target not in sources:
                        sources[target] = [candidate]
                        changed = True
        return {species: tuple(values) for species, values in sources.items()}

    @staticmethod
    def _species_name(species: str) -> str:
        return " ".join(word.capitalize() for word in species.removeprefix("SPECIES_").split("_"))


def map_stage(map_name: str) -> int:
    normalized = map_name.upper().removeprefix("MAP_")
    route = re.match(r"ROUTE(\d+)", normalized)
    if route:
        number = int(route.group(1))
        if number <= 104 or number == 116:
            return 0
        if number <= 110 or number == 117:
            return 1
        if number <= 114:
            return 2
        if number == 115:
            return 3
        if number <= 123:
            return 5
        if number <= 128:
            return 6
        return 7
    stages = (
        (0, ("PETALBURG_WOODS", "RUSTURF_TUNNEL")),
        (1, ("DEWFORD", "GRANITE_CAVE", "SLATEPORT")),
        (2, ("FIERY_PATH", "JAGGED_PASS", "METEOR_FALLS", "MIRAGE_TOWER")),
        (5, ("LILYCOVE", "MT_PYRE", "SAFARI_ZONE", "MAGMA_HIDEOUT", "NEW_MAUVILLE", "ABANDONED_SHIP")),
        (6, ("MOSSDEEP", "SHOAL_CAVE", "SEAFLOOR_CAVERN", "UNDERWATER", "SOOTOPOLIS", "CAVE_OF_ORIGIN")),
        (7, ("PACIFIDLOG", "SKY_PILLAR")),
    )
    for stage, fragments in stages:
        if any(fragment in normalized for fragment in fragments):
            return stage
    return 8