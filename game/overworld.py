import math
import re
from collections import OrderedDict
from typing import Any

from retroarch_overlay.core.contracts import MemoryReader
from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.models import PanelAction, PanelRow, PanelSection

from .achievements import (
    ACHIEVEMENT_TITLES,
    GYM_MISSABLES,
    NEARBY_ACHIEVEMENTS,
    TRICK_HOUSE_MISSABLES,
)
from .feebas import feebas_spot_ids, tile_in_front
from .poc import FINAL_TARGET, POC_GATES, PocPlanner
from .state import PokemonState
from .tracker import TrainingAreaTracker


BADGE_FLAG_START = 0x867
DEWFORD_TREND_SEED_OFFSET = 0x2E66
# gObjectEvents[0].currentCoords. 0x0203F360 reads as a constant zero;
# the player object lives at gObjectEvents = 0x02037350.
PLAYER_POSITION_ADDRESS = 0x02037360
OBJECT_EVENTS_ADDRESS = 0x02037350
OBJECT_EVENT_SIZE = 0x24
OBJECT_EVENTS_COUNT = 16
# gPlayerAvatar is defined directly after gObjectEvents[OBJECT_EVENTS_COUNT].
PLAYER_AVATAR_ADDRESS = 0x02037590
PLAYER_AVATAR_FLAG_SURFING = 1 << 3
PLAYER_AVATAR_FLAG_UNDERWATER = 1 << 4
# OBJ_EVENT_GFX_BRENDAN_FISHING / OBJ_EVENT_GFX_MAY_FISHING while a rod is out.
FISHING_GRAPHICS_IDS = frozenset((137, 138))
ROAMER_OFFSET = 0x31DC
ROAMER_SIZE = 0x1C
ROAMER_LOCATION_ADDRESS = 0x0203BC86
ITEM_POCKET_OFFSET = 0x560
ITEM_POCKET_SIZE = 80
BERRY_POCKET_OFFSET = 0x790
BERRY_POCKET_SIZE = 184
DECORATION_INVENTORY_OFFSET = 0x2734
DECORATION_INVENTORY_SIZE = 150
SECRET_BASE_DECORATIONS_OFFSET = 0x1AAE
SECRET_BASE_DECORATIONS_SIZE = 16
HM_FLAGS = (0x89, 0x6E, 0x7A, 0x6A, 0x6D, 0x6B, 0x7B, 0x138)
FLUTE_ITEM_IDS = frozenset(range(39, 44))


def _normalize_map_name(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.removeprefix("MAP_").upper())


def _display_constant(value: str, prefix: str) -> str:
    words = value.removeprefix(prefix).split("_")
    label = " ".join(word.capitalize() for word in words)
    return re.sub(r"(?<=\D)(?=\d)", " ", label)


class OverworldPresenter:
    def __init__(
        self,
        *,
        account_progress: RAProgress | None,
        field_definitions: dict[str, dict[str, Any]],
        national_dex: dict[str, int],
        species_by_id: dict[int, str],
        flag_ids: dict[str, int],
        route_trackers: dict[
            str,
            tuple[dict[str, tuple[int, ...]], dict[str, int], dict[str, int]],
        ],
        item_locations: dict[str, tuple[tuple[Any, ...], ...]],
        rematches: dict[str, tuple[tuple[int, str], ...]],
        fishing_spots: dict[tuple[int, int], int],
        exp_yields: dict[str, int],
        growth_rates: dict[str, str],
        training_tracker: TrainingAreaTracker,
        poc_planner: PocPlanner,
    ) -> None:
        self._account_progress = account_progress
        self._field_definitions = field_definitions
        self._national_dex = national_dex
        self._species_by_id = species_by_id
        self._flag_ids = flag_ids
        self._route_trackers = route_trackers
        self._item_locations = item_locations
        self._rematches = rematches
        self._fishing_spots = fishing_spots
        self._exp_yields = exp_yields
        self._growth_rates = growth_rates
        self._training_tracker = training_tracker
        self._poc_planner = poc_planner
        self._fishing_tile: tuple[str, bytes, int] | None = None
        self._nearby_achievements = {
            map_name: tuple(
                achievement
                for achievement in NEARBY_ACHIEVEMENTS
                if achievement.map_name == map_name
            )
            for map_name in {
                achievement.map_name for achievement in NEARBY_ACHIEVEMENTS
            }
        }

    def missable_section(
        self, map_name: str, event_flags: bytes
    ) -> PanelSection | None:
        gym = GYM_MISSABLES.get(map_name)
        if gym is not None:
            _, title, badge_index, leader = gym
            if not self.flag_is_set(event_flags, BADGE_FLAG_START + badge_index):
                tracker = self._route_trackers.get(map_name)
                trainer_groups = tracker[0] if tracker is not None else {}
                missing = [
                    name
                    for name, trainer_ids in trainer_groups.items()
                    if leader.upper().replace(" & ", "_AND_") not in name
                    and not any(
                        self.flag_is_set(event_flags, 0x500 + trainer_id)
                        for trainer_id in trainer_ids
                    )
                ]
                detail = (
                    f"Defeat {len(missing)} remaining trainer(s) before {leader}"
                    if missing
                    else f"Confirm every trainer is defeated before {leader}"
                )
                return PanelSection(
                    f"MISSABLE · {title}",
                    (PanelRow(detail),),
                    alert=True,
                    priority=0,
                    role="urgent",
                    key="missable",
                )
        trick_house = TRICK_HOUSE_MISSABLES.get(map_name)
        if trick_house is not None:
            _, title = trick_house
            tracker = self._route_trackers.get(map_name)
            if tracker is not None:
                trainer_groups, item_flags, _ = tracker
                trainers_left = sum(
                    not any(
                        self.flag_is_set(event_flags, 0x500 + trainer_id)
                        for trainer_id in trainer_ids
                    )
                    for trainer_ids in trainer_groups.values()
                )
                items_left = sum(
                    not self.flag_is_set(event_flags, flag_id)
                    for flag_id in item_flags.values()
                )
                if trainers_left or items_left:
                    return PanelSection(
                        f"MISSABLE · {title}",
                        (
                            PanelRow(
                                f"Before finishing: {trainers_left} trainer(s), "
                                f"{items_left} item(s) remain"
                            ),
                        ),
                        alert=True,
                        priority=0,
                        role="urgent",
                        key="missable",
                    )
        return None

    def nearby_achievement_section(
        self, map_name: str, event_flags: bytes
    ) -> PanelSection | None:
        pending = []
        account_unlocked = (
            self._account_progress.unlocked_ids
            if self._account_progress
            else frozenset()
        )
        tracker = self._route_trackers.get(map_name)
        trainer_groups = tracker[0] if tracker is not None else {}
        for achievement in self._nearby_achievements.get(map_name, ()):
            if achievement.achievement_id in account_unlocked:
                continue
            if achievement.event_flag is not None:
                flag_id = self._flag_ids.get(achievement.event_flag)
                complete = flag_id is not None and self.flag_is_set(event_flags, flag_id)
            else:
                trainer_ids = trainer_groups.get(
                    achievement.trainer_prefix or "", ()
                )
                complete = any(
                    self.flag_is_set(event_flags, 0x500 + trainer_id)
                    for trainer_id in trainer_ids
                )
            if not complete:
                pending.append(PanelRow(achievement.title))
        if not pending:
            return None
        return PanelSection(
            "RA nearby",
            tuple(pending[:3]),
            priority=12,
            role="goals",
            key="nearby-achievements",
        )

    def achievement_section(self) -> PanelSection | None:
        if self._account_progress is None:
            return None
        rows = []
        if self._account_progress.message:
            rows.append(PanelRow(self._account_progress.message))
        else:
            unlocked = self._account_progress.unlocked_ids & ACHIEVEMENT_TITLES.keys()
            rows.append(
                PanelRow(
                    f"{len(unlocked)}/{len(ACHIEVEMENT_TITLES)} tracked unlocked · "
                    f"{self._account_progress.username}"
                )
            )
            rows.extend(
                PanelRow(f"{ACHIEVEMENT_TITLES[achievement_id]} · account", True)
                for achievement_id in sorted(unlocked)
            )
        return PanelSection(
            "RetroAchievements",
            tuple(rows),
            preview_limit=5,
            priority=45,
            role="goals",
            compact_rows=tuple(rows[:1]),
            key="retroachievements",
        )

    def roamer_section(
        self,
        memory: MemoryReader,
        save_block_1: int,
        map_group: int,
        map_number: int,
    ) -> PanelSection | None:
        roamer = memory.read_memory(save_block_1 + ROAMER_OFFSET, ROAMER_SIZE)
        if not roamer[0x13]:
            return None
        if memory.read_memory(ROAMER_LOCATION_ADDRESS, 2) != bytes(
            (map_group, map_number)
        ):
            return None
        species_id = int.from_bytes(roamer[0x08:0x0A], "little")
        species = self._species_by_id.get(species_id, f"Species {species_id}")
        return PanelSection(
            "RA · Flying Through the Eons",
            (
                PanelRow(
                    f"{_display_constant(species, 'SPECIES_')} IS ON THIS ROUTE · "
                    f"Lv {roamer[0x0C]} · "
                    f"HP {int.from_bytes(roamer[0x0A:0x0C], 'little')}"
                ),
            ),
            priority=1,
            role="urgent",
            key="roamer",
        )

    def collection_section(
        self, memory: MemoryReader, save_block_1: int, event_flags: bytes
    ) -> PanelSection:
        items = memory.read_memory(
            save_block_1 + ITEM_POCKET_OFFSET, ITEM_POCKET_SIZE
        )
        item_ids = {
            int.from_bytes(items[offset : offset + 2], "little")
            for offset in range(0, len(items), 4)
        }
        berries = memory.read_memory(
            save_block_1 + BERRY_POCKET_OFFSET, BERRY_POCKET_SIZE
        )
        berry_count = sum(
            bool(int.from_bytes(berries[offset : offset + 2], "little"))
            for offset in range(0, len(berries), 4)
        )
        decorations = memory.read_memory(
            save_block_1 + DECORATION_INVENTORY_OFFSET,
            DECORATION_INVENTORY_SIZE,
        )
        furniture_count = sum(bool(value) for value in decorations[:30])
        doll_count = sum(bool(value) for value in decorations[100:140])
        placed = memory.read_memory(
            save_block_1 + SECRET_BASE_DECORATIONS_OFFSET,
            SECRET_BASE_DECORATIONS_SIZE,
        )
        hm_count = sum(self.flag_is_set(event_flags, flag) for flag in HM_FLAGS)
        flute_count = len(item_ids & FLUTE_ITEM_IDS)
        placed_count = sum(bool(value) for value in placed)
        details = (
            PanelRow(f"HMs {hm_count}/8"),
            PanelRow(f"Flutes {flute_count}/5"),
            PanelRow(f"Berry pocket species {berry_count}/46"),
            PanelRow(f"Secret Base furniture {furniture_count}/30"),
            PanelRow(f"Secret Base dolls {doll_count}/40"),
            PanelRow(f"Secret Base placed decorations {placed_count}/16"),
        )
        return PanelSection(
            "Collections",
            (
                PanelRow(
                    f"HMs {hm_count}/8 · Flutes {flute_count}/5 · "
                    f"Berries {berry_count}/46"
                ),
                PanelRow(
                    f"Furniture {furniture_count}/30 · Dolls {doll_count}/40 · "
                    f"Base placed {placed_count}/16"
                ),
            ),
            actions=(
                PanelAction(
                    "OPEN COLLECTION DETAILS",
                    "Emerald Collections",
                    details,
                    key="collection-details",
                ),
            ),
            priority=50,
            role="goals",
            compact_rows=(PanelRow(f"HMs {hm_count}/8 · Berries {berry_count}/46"),),
            key="collections",
        )

    @property
    def fishing_spots(self) -> dict[tuple[int, int], int]:
        return self._fishing_spots

    def feebas_section(
        self, memory: MemoryReader, save_block_1: int, map_name: str
    ) -> PanelSection | None:
        if map_name != "Route119":
            return None
        seed = int.from_bytes(
            memory.read_memory(
                save_block_1 + DEWFORD_TREND_SEED_OFFSET, 2
            ),
            "little",
        )
        active_spots = feebas_spot_ids(seed)
        position = memory.read_memory(PLAYER_POSITION_ADDRESS, 9)
        x = int.from_bytes(position[0:2], "little", signed=True)
        y = int.from_bytes(position[2:4], "little", signed=True)
        target = tile_in_front(x, y, position[8])
        spot_id = self._fishing_spots.get(target)
        coordinates_by_spot = {
            spot: coordinates for coordinates, spot in self._fishing_spots.items()
        }
        details = tuple(
            PanelRow(
                f"Spot {spot} · "
                f"({coordinates_by_spot[spot][0]},{coordinates_by_spot[spot][1]})"
            )
            for spot in dict.fromkeys(active_spots)
            if spot in coordinates_by_spot
        )
        active = spot_id in active_spots
        return PanelSection(
            "RA · One Tile Away from Beauty" if active else "Feebas tiles",
            (
                PanelRow(
                    f"VALID TILE · spot {spot_id} · 50% Feebas"
                    if active
                    else f"Facing ({target[0]},{target[1]}) · not an active tile"
                ),
            ),
            actions=(
                PanelAction(
                    "OPEN FEEBAS TILES",
                    "Route 119 Feebas Tiles",
                    details,
                    key="feebas-tiles",
                ),
            ),
            priority=3 if active else 35,
            role="urgent" if active else "goals",
            key="feebas",
        )

    def poc_section(
        self,
        caught_flags: bytes,
        event_flags: bytes,
        encounter: dict[str, Any] | None,
        location: str,
        party: tuple[PokemonState, ...],
        training_method: str | None = None,
    ) -> PanelSection:
        caught_count = self._poc_planner.caught_count(
            caught_flags, event_flags
        )
        next_gate = next(
            (
                (gate.leader, gate.target)
                for gate in POC_GATES
                if not self.flag_is_set(
                    event_flags, BADGE_FLAG_START + gate.badge
                )
            ),
            None,
        )
        if next_gate is None:
            text = f"Final goal  {caught_count}/{FINAL_TARGET}"
        else:
            leader, target = next_gate
            ready = "READY" if caught_count >= target else f"need {target - caught_count}"
            text = f"Next: {leader}  {caught_count}/{target}  {ready}"
        return PanelSection(
            "Professor Oak Challenge",
            (PanelRow(text),),
            actions=(
                PanelAction(
                    "OPEN POC DETAILS",
                    "Professor Oak Challenge",
                    self._poc_detail_rows(
                        caught_flags,
                        event_flags,
                        encounter,
                        location,
                        party,
                        training_method,
                    ),
                    compact=True,
                    key="poc-details",
                ),
                PanelAction(
                    "OPEN ACQUISITION PLAN",
                    "Professor Oak Acquisition Plan",
                    self._poc_planner.rows(
                        caught_flags,
                        event_flags,
                        encounter["map"] if encounter is not None else "",
                        self.flag_is_set,
                    ),
                    key="acquisition-plan",
                ),
            ),
            priority=5,
            role="goals",
            compact_rows=(PanelRow(text),),
            key="professor-oak-challenge",
        )

    def _poc_detail_rows(
        self,
        caught_flags: bytes,
        event_flags: bytes,
        encounter: dict[str, Any] | None,
        location: str,
        party: tuple[PokemonState, ...],
        training_method: str | None = None,
    ) -> tuple[PanelRow, ...]:
        rows = [PanelRow(f"CURRENT AREA · {location}".upper())]
        caught_count = self._poc_planner.caught_count(
            caught_flags, event_flags
        )
        next_gate = next(
            (
                (gate.leader, gate.target)
                for gate in POC_GATES
                if not self.flag_is_set(
                    event_flags, BADGE_FLAG_START + gate.badge
                )
            ),
            None,
        )
        rows.append(PanelRow(f"NEXT DEX GATE · {caught_count} CAUGHT"))
        if next_gate is None:
            rows.append(PanelRow(f"Final goal · {caught_count}/{FINAL_TARGET}"))
        else:
            leader, target = next_gate
            state = "ready" if caught_count >= target else f"{target - caught_count} left"
            rows.append(PanelRow(f"{leader} · {caught_count}/{target} · {state}"))
        if encounter is not None:
            route_rows = self.route_encounter_detail_rows(encounter, caught_flags)
            if route_rows:
                rows.append(PanelRow("MISSING IN THIS AREA"))
                rows.extend(route_rows)
            rows.extend(
                self.route_training_rows(
                    encounter, location, party, training_method
                )
            )
        else:
            rows.append(PanelRow("No wild encounter data for this area."))
            rows.extend(
                self.route_training_rows(None, location, party, training_method)
            )
        return tuple(rows)

    def completion_sections(
        self,
        memory: MemoryReader,
        save_block_1: int,
        map_name: str,
        flags: bytes,
        rematches: bytes,
    ) -> tuple[PanelSection, ...]:
        tracker = self._route_trackers.get(map_name)
        if tracker is None:
            return ()
        trainer_groups, item_flags, objective_flags = tracker
        sections = []
        if trainer_groups:
            missing = [
                _display_constant(name, "TRAINER_")
                for name, ids in trainer_groups.items()
                if not any(
                    self.flag_is_set(flags, 0x500 + trainer_id)
                    for trainer_id in ids
                )
            ]
            sections.append(
                self._checklist_section(
                    "Route trainers",
                    len(trainer_groups),
                    missing,
                    "route-trainers",
                )
            )
        map_item_locations = self._item_locations.get(map_name, ())
        if map_item_locations:
            player_x, player_y = self._player_position(memory, save_block_1)
            missing = []
            for item_name, item_x, item_y, flag_id, hidden in map_item_locations:
                if self.flag_is_set(flags, int(flag_id)):
                    continue
                kind = "hidden" if hidden else "item"
                missing.append(
                    (
                        abs(int(item_x) - player_x) + abs(int(item_y) - player_y),
                        f"{item_name} · ({item_x},{item_y}) · {kind}",
                    )
                )
            missing.sort(key=lambda entry: entry[0])
            sections.append(
                self._checklist_section(
                    f"Route items · You ({player_x},{player_y})",
                    len(map_item_locations),
                    [text for _, text in missing],
                    "route-items",
                )
            )
        elif item_flags:
            missing = [
                name
                for name, flag_id in item_flags.items()
                if not self.flag_is_set(flags, flag_id)
            ]
            sections.append(
                self._checklist_section(
                    "Route items",
                    len(item_flags),
                    missing,
                    "route-items",
                )
            )
        missing_objectives = [
            name
            for name, flag_id in objective_flags.items()
            if not self.flag_is_set(flags, flag_id)
        ]
        if missing_objectives:
            sections.append(
                PanelSection(
                    "Nearby objectives",
                    tuple(PanelRow(name) for name in missing_objectives),
                    3,
                    role="area",
                    key="nearby-objectives",
                )
            )
        ready_rematches = [
            name
            for index, name in self._rematches.get(
                _normalize_map_name(map_name), ()
            )
            if index < len(rematches) and rematches[index]
        ]
        if ready_rematches:
            sections.append(
                PanelSection(
                    "Rematches ready",
                    tuple(PanelRow(name) for name in ready_rematches),
                    3,
                    role="area",
                    key="rematches-ready",
                )
            )
        return tuple(sections)

    def route_encounter_detail_rows(
        self, encounter: dict[str, Any], caught_flags: bytes
    ) -> tuple[PanelRow, ...]:
        rows = []
        for field_name, title in (
            ("land_mons", "Land"),
            ("water_mons", "Water"),
            ("rock_smash_mons", "Rock Smash"),
        ):
            if field_name not in encounter:
                continue
            for species, values in self.encounter_species(
                field_name, encounter[field_name]
            ).items():
                if self.is_caught(species, caught_flags):
                    continue
                rows.append(
                    PanelRow(
                        f"{title}: {_display_constant(species, 'SPECIES_')} · "
                        f"Lv {values['min']}-{values['max']} · "
                        f"{values['chance']}%",
                        False,
                    )
                )
        fishing = encounter.get("fishing_mons")
        if fishing is not None:
            for rod_name, indexes in self._field_definitions["fishing_mons"][
                "groups"
            ].items():
                title = _display_constant(rod_name.upper(), "")
                for species, values in self.encounter_species(
                    "fishing_mons", fishing, indexes
                ).items():
                    if self.is_caught(species, caught_flags):
                        continue
                    rows.append(
                        PanelRow(
                            f"{title}: {_display_constant(species, 'SPECIES_')} · "
                            f"Lv {values['min']}-{values['max']} · "
                            f"{values['chance']}%",
                            False,
                        )
                    )
        return tuple(rows)

    def training_method(self, memory: MemoryReader, map_name: str) -> str:
        """Encounter table the player is using now: land, water, or fishing."""
        avatar = memory.read_memory(PLAYER_AVATAR_ADDRESS, 6)
        if len(avatar) != 6 or avatar[5] >= OBJECT_EVENTS_COUNT:
            raise ValueError("player avatar read was invalid")
        player = memory.read_memory(
            OBJECT_EVENTS_ADDRESS + avatar[5] * OBJECT_EVENT_SIZE, 0x14
        )
        if len(player) != 0x14:
            raise ValueError("player object read was incomplete")
        water = avatar[0] & (
            PLAYER_AVATAR_FLAG_SURFING | PLAYER_AVATAR_FLAG_UNDERWATER
        )
        # The rod sprite is only up while casting, so keep treating the player
        # as fishing between casts until they leave that tile.
        tile = (map_name, bytes(player[0x10:0x14]), water)
        if player[5] in FISHING_GRAPHICS_IDS:
            self._fishing_tile = tile
        elif tile != self._fishing_tile:
            self._fishing_tile = None
        if self._fishing_tile is not None:
            return "fishing_mons"
        return "water_mons" if water else "land_mons"

    def route_training_rows(
        self,
        encounter: dict[str, Any] | None,
        location: str,
        party: tuple[PokemonState, ...],
        training_method: str | None = None,
    ) -> tuple[PanelRow, ...]:
        current_rows = []
        current_exp: dict[str, float] = {}
        cache_changed = False
        for field_name, title, cache_best in (
            ("land_mons", "Land", True),
            ("water_mons", "Water", True),
            ("rock_smash_mons", "Rock Smash", False),
            ("fishing_mons", "Fishing", True),
        ):
            if encounter is None or field_name not in encounter:
                continue
            average_exp = self.average_exp_per_encounter(
                field_name, encounter[field_name]
            )
            if not average_exp:
                continue
            current_exp[field_name] = average_exp
            if cache_best and self._training_tracker.observe(
                field_name, average_exp, location
            ):
                cache_changed = True
            encounter_rate = encounter[field_name].get("encounter_rate")
            if encounter_rate:
                current_rows.append(
                    PanelRow(
                        f"{title} · {average_exp:.1f} base solo XP · "
                        f"{encounter_rate}% · ~{100 / encounter_rate:.1f} steps"
                    )
                )
            else:
                current_rows.append(
                    PanelRow(f"{title} · {average_exp:.1f} base solo XP")
                )
        if cache_changed:
            self._training_tracker.save()
        rows = []
        if current_rows:
            rows.append(PanelRow("CURRENT AREA EXP"))
            rows.extend(current_rows)
        best_areas = self._training_tracker.areas
        if best_areas:
            rows.append(PanelRow("BEST LEVELING AREAS SEEN"))
            for field_name, title in (
                ("land_mons", "Land"),
                ("water_mons", "Water"),
                ("fishing_mons", "Fishing"),
            ):
                best = best_areas.get(field_name)
                if best is not None:
                    rows.append(PanelRow(f"{title} · {best[1]} · {best[0]:.1f} XP"))
        method_titles = {
            "land_mons": "Land",
            "water_mons": "Water",
            "fishing_mons": "Fishing",
        }
        # Project against what the player is doing here; the best area seen is
        # only a fallback for maps without encounters for that activity.
        training_method = training_method or "land_mons"
        if training_method in current_exp:
            gain_exp = current_exp[training_method]
            heading = (
                f"PARTY TO NEXT LEVEL · {method_titles[training_method]} · "
                f"{location}"
            )
        else:
            best_method = max(
                best_areas.items(), key=lambda entry: entry[1][0], default=None
            )
            gain_exp = best_method[1][0] if best_method is not None else 0
            if best_method is not None:
                field_name, (_, best_location) = best_method
                heading = (
                    f"PARTY TO NEXT LEVEL · BEST SEEN · "
                    f"{method_titles[field_name]} · {best_location}"
                )
        if gain_exp:
            rows.append(PanelRow(heading.upper()))
            for member in party:
                if member.level >= 100:
                    rows.append(
                        PanelRow(
                            f"{_display_constant(member.species, 'SPECIES_')} · "
                            "Lv 100 · MAX"
                        )
                    )
                    continue
                needed = max(
                    0,
                    self.experience_for_level(member.species, member.level + 1)
                    - member.experience,
                )
                expected_gain = gain_exp
                modifiers = ["solo"]
                if member.held_item_id == 182:
                    expected_gain /= 2
                    modifiers = ["passive Exp. Share"]
                if member.held_item_id == 197:
                    expected_gain = math.floor(expected_gain * 1.5)
                    modifiers.append("Lucky Egg")
                if member.is_traded:
                    expected_gain = math.floor(expected_gain * 1.5)
                    modifiers.append("traded")
                encounters = (
                    math.ceil(needed / expected_gain) if expected_gain else 0
                )
                rows.append(
                    PanelRow(
                        f"{_display_constant(member.species, 'SPECIES_')} "
                        f"{member.level}→{member.level + 1} · {needed} XP · "
                        f"~{expected_gain:.1f}/fight · ~{encounters} fights · "
                        f"{', '.join(modifiers)}"
                    )
                )
        return tuple(rows)

    def average_exp_per_encounter(
        self, field_name: str, encounter: dict[str, Any]
    ) -> float:
        rates = self._field_definitions[field_name]["encounter_rates"]
        weighted_exp = 0
        total_chance = 0
        for rate, mon in zip(rates, encounter["mons"]):
            exp_yield = self._exp_yields.get(mon["species"], 0)
            levels = range(mon["min_level"], mon["max_level"] + 1)
            level_exp = (
                sum(exp_yield * level // 7 for level in levels) / len(levels)
            )
            weighted_exp += rate * level_exp
            total_chance += rate
        return weighted_exp / total_chance if total_chance else 0

    def encounter_species(
        self,
        field_name: str,
        encounter: dict[str, Any],
        indexes: list[int] | None = None,
    ) -> OrderedDict[str, dict[str, int]]:
        definition = self._field_definitions[field_name]
        rates = definition["encounter_rates"]
        selected = (
            indexes
            if indexes is not None
            else list(range(len(encounter["mons"])))
        )
        species: OrderedDict[str, dict[str, int]] = OrderedDict()
        for index in selected:
            mon = encounter["mons"][index]
            entry = species.setdefault(
                mon["species"],
                {
                    "min": mon["min_level"],
                    "max": mon["max_level"],
                    "chance": 0,
                },
            )
            entry["min"] = min(entry["min"], mon["min_level"])
            entry["max"] = max(entry["max"], mon["max_level"])
            entry["chance"] += rates[index]
        return species

    def encounter_section(
        self,
        title: str,
        key: str,
        field_name: str,
        encounter: dict[str, Any],
        caught_flags: bytes,
        indexes: list[int] | None = None,
    ) -> PanelSection:
        species = self.encounter_species(field_name, encounter, indexes)
        rows = tuple(
            PanelRow(
                f"{_display_constant(name, 'SPECIES_')}  "
                f"Lv {values['min']}-{values['max']}  {values['chance']}%",
                self.is_caught(name, caught_flags),
            )
            for name, values in species.items()
        )
        encounter_rate = encounter.get("encounter_rate")
        heading = (
            f"{title} · rate {encounter_rate}"
            if encounter_rate is not None
            else title
        )
        return PanelSection(
            heading,
            rows,
            role="area",
            compact_rows=(PanelRow(f"{len(rows)} species"),),
            key=key,
        )

    def is_caught(self, species: str, caught_flags: bytes) -> bool:
        national_number = self._national_dex[species]
        bit_index = national_number - 1
        return bool(
            caught_flags[bit_index // 8] & (1 << (bit_index % 8))
        )

    def experience_for_level(self, species: str, level: int) -> int:
        if level <= 1:
            return level
        growth_rate = self._growth_rates[species]
        if growth_rate == "GROWTH_FAST":
            return 4 * level**3 // 5
        if growth_rate == "GROWTH_MEDIUM_FAST":
            return level**3
        if growth_rate == "GROWTH_MEDIUM_SLOW":
            return 6 * level**3 // 5 - 15 * level**2 + 100 * level - 140
        if growth_rate == "GROWTH_SLOW":
            return 5 * level**3 // 4
        if growth_rate == "GROWTH_ERRATIC":
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

    @staticmethod
    def flag_is_set(flags: bytes, flag_id: int) -> bool:
        if flag_id < 0 or flag_id // 8 >= len(flags):
            return False
        return bool(flags[flag_id // 8] & (1 << (flag_id % 8)))

    @staticmethod
    def _player_position(
        memory: MemoryReader, save_block_1: int
    ) -> tuple[int, int]:
        position = memory.read_memory(save_block_1, 4)
        return (
            int.from_bytes(position[:2], "little", signed=True),
            int.from_bytes(position[2:4], "little", signed=True),
        )

    @staticmethod
    def _checklist_section(
        title: str,
        total: int,
        missing: list[str],
        key: str,
    ) -> PanelSection:
        rows = [PanelRow(f"{total - len(missing)}/{total} complete")]
        rows.extend(PanelRow(name, False) for name in missing)
        return PanelSection(
            title,
            tuple(rows),
            4,
            role="area",
            compact_rows=(rows[0],),
            key=key,
        )