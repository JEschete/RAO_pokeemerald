from dataclasses import dataclass

from retroarch_overlay.models import PanelAction, PanelRow, PanelSection


@dataclass(frozen=True, slots=True)
class LegendaryTarget:
    species: str
    location: str
    availability_flag: str
    defeated_flag: str
    locked_reason: str


TARGETS = (
    LegendaryTarget("SPECIES_RAYQUAZA", "Sky Pillar", "FLAG_SOOTOPOLIS_ARCHIE_MAXIE_LEAVE", "FLAG_DEFEATED_RAYQUAZA", "Resolve the Sootopolis weather crisis"),
    LegendaryTarget("SPECIES_GROUDON", "Terra Cave", "FLAG_SYS_GAME_CLEAR", "FLAG_DEFEATED_GROUDON", "Enter the Hall of Fame"),
    LegendaryTarget("SPECIES_KYOGRE", "Marine Cave", "FLAG_SYS_GAME_CLEAR", "FLAG_DEFEATED_KYOGRE", "Enter the Hall of Fame"),
    LegendaryTarget("SPECIES_REGIROCK", "Desert Ruins", "FLAG_SYS_REGIROCK_PUZZLE_COMPLETED", "FLAG_DEFEATED_REGIROCK", "Open the Sealed Chamber and solve Desert Ruins"),
    LegendaryTarget("SPECIES_REGICE", "Island Cave", "FLAG_SYS_BRAILLE_REGICE_COMPLETED", "FLAG_DEFEATED_REGICE", "Open the Sealed Chamber and solve Island Cave"),
    LegendaryTarget("SPECIES_REGISTEEL", "Ancient Tomb", "FLAG_SYS_REGISTEEL_PUZZLE_COMPLETED", "FLAG_DEFEATED_REGISTEEL", "Open the Sealed Chamber and solve Ancient Tomb"),
)


class LegendaryDashboard:
    def __init__(self, flag_ids: dict[str, int], national_dex: dict[str, int]) -> None:
        self._flag_ids = flag_ids
        self._national_dex = national_dex

    def section(
        self,
        flags: bytes,
        caught_flags: bytes,
        roamer: bytes,
    ) -> PanelSection:
        rows = []
        caught_count = 0
        for target in TARGETS:
            caught = self._caught(target.species, caught_flags)
            if caught:
                caught_count += 1
                state = "Caught"
            elif self._flag(flags, target.defeated_flag):
                state = "Defeated uncaught"
            elif self._flag(flags, target.availability_flag):
                state = "Available"
            else:
                state = f"Locked · {target.locked_reason}"
            rows.append(
                PanelRow(
                    f"{self._name(target.species)} · {target.location} · {state}",
                    caught,
                )
            )

        lati_species = int.from_bytes(roamer[0x08:0x0A], "little") if len(roamer) >= 0x14 else 0
        lati_name = {407: "SPECIES_LATIAS", 408: "SPECIES_LATIOS"}.get(lati_species)
        if lati_name is None:
            lati_name = next(
                (
                    species
                    for species in ("SPECIES_LATIAS", "SPECIES_LATIOS")
                    if self._caught(species, caught_flags)
                ),
                None,
            )
        if lati_name is not None:
            caught = self._caught(lati_name, caught_flags)
            if caught:
                caught_count += 1
                state = "Caught"
            elif len(roamer) >= 0x14 and roamer[0x13]:
                state = f"Roaming · Lv {roamer[0x0C]} · HP {int.from_bytes(roamer[0x0A:0x0C], 'little')}"
            elif self._flag(flags, "FLAG_DEFEATED_LATIAS_OR_LATIOS"):
                state = "Defeated uncaught"
            else:
                state = "Roamer inactive"
            rows.append(PanelRow(f"{self._name(lati_name)} · Hoenn routes · {state}", caught))
        else:
            state = "Choose after Hall of Fame" if self._flag(flags, "FLAG_SYS_GAME_CLEAR") else "Locked · Enter the Hall of Fame"
            rows.append(PanelRow(f"Latios / Latias · {state}"))

        return PanelSection(
            "Vanilla legendaries",
            (PanelRow(f"Caught {caught_count}/7 · no event-ticket species"),),
            actions=(
                PanelAction(
                    "OPEN LEGENDARY DASHBOARD",
                    "Vanilla Legendary Dashboard",
                    tuple(rows),
                    key="legendary-details",
                ),
            ),
            priority=25,
            role="goals",
            compact_rows=(PanelRow(f"Legendaries {caught_count}/7"),),
            key="legendaries",
        )

    def _flag(self, flags: bytes, name: str) -> bool:
        flag_id = self._flag_ids.get(name)
        return flag_id is not None and flag_id // 8 < len(flags) and bool(flags[flag_id // 8] & (1 << (flag_id % 8)))

    def _caught(self, species: str, caught_flags: bytes) -> bool:
        number = self._national_dex.get(species)
        if number is None or number <= 0:
            return False
        bit = number - 1
        return bit // 8 < len(caught_flags) and bool(caught_flags[bit // 8] & (1 << (bit % 8)))

    @staticmethod
    def _name(species: str) -> str:
        return " ".join(word.capitalize() for word in species.removeprefix("SPECIES_").split("_"))