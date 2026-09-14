import logging
import re
from dataclasses import replace
from hashlib import blake2b
from collections.abc import Callable
from pathlib import Path
from typing import Any

from retroarch_overlay.core.contracts import MemoryReader
from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.models import (
    GameDisplaySpec,
    MapDocument,
    MapOverlay,
    MapPosition,
    OverlaySnapshot,
    PanelRow,
    PanelSection,
    RetroArchStatus,
)
from retroarch_overlay.retroarch import RetroArchError

from .battle_view import BattleSnapshotBuilder
from .contest import POKEBLOCKS_SIZE, decode_pokeblocks
from .daycare import DaycareDashboard
from .factory import FactoryAdvisor
from .frontier import BattleFrontierDashboard
from .hunt import HuntTracker
from .icons import SpeciesIconCache
from .journal import EventDetector, SessionJournal
from .knowledge import EmeraldKnowledge
from .matchcall import MatchCallDashboard
from .pickup import PickupWatcher
from .repel import repel_section
from .wildiv import WildScout, build_family_map
from .legendary import LegendaryDashboard
from .mapdata import EmeraldMapCatalog
from .mapoverlays import EmeraldOverlayBuilder, feebas_waypoints
from .worldmap import (
    load_region_sections,
    parse_region_layout,
    section_positions,
    world_waypoints,
)
from .manifest import RA_GAME_ID, RA_HASHES
from .memory import (
    EWRAM_END,
    EWRAM_START,
    SAVE_BLOCK_1_POINTER,
    SAVE_BLOCK_2_POINTER,
    SavePointers,
    verify_save_pointers,
)
from .navigator import ObjectiveNavigator
from .feebas import feebas_spot_ids
from .overworld import (
    DEWFORD_TREND_SEED_OFFSET,
    OverworldPresenter,
    ROAMER_OFFSET,
    ROAMER_SIZE,
)
from .poc import PocPlanner
from .presenter import EmeraldPresenter
from .rtc_events import RtcEventDashboard
from .state import PokemonState, decode_party
from .tracker import BattleParticipationTracker, TrainingAreaTracker


LOGGER = logging.getLogger(__name__)

PLAYER_POS_OFFSET = 0x00
FEEBAS_MAP_NAME = "Route119"
POKEDEX_OWNED_OFFSET = 0x28
DEX_FLAG_BYTES = 52
FLAGS_OFFSET = 0x1270
FLAGS_SIZE = 0x160
REMATCHES_OFFSET = 0x9CA
REMATCHES_SIZE = 100
PLAYER_PARTY_COUNT_ADDRESS = 0x020244E9
PLAYER_PARTY_ADDRESS = 0x020244EC
PARTY_SIZE = 6
POKEMON_SIZE = 0x64
POKEBLOCKS_OFFSET = 0x848
VARS_OFFSET = 0x139C
VARS_START = 0x4000


def _normalize_map_name(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.removeprefix("MAP_").upper())


def _display_constant(value: str, prefix: str) -> str:
    words = value.removeprefix(prefix).split("_")
    label = " ".join(word.capitalize() for word in words)
    return re.sub(r"(?<=\D)(?=\d)", " ", label)


def _display_map_name(value: str) -> str:
    parts = []
    for part in value.split("_"):
        label = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=\D)(?=\d)", " ", part)
        parts.append(label.replace("Pokemon", "Pokémon"))
    return " · ".join(parts)


class EmeraldAdapter:
    name = "Pokémon Emerald"
    DISPLAY_SPEC = GameDisplaySpec("gba", 240, 160, "integer", 6)
    ra_game_id = RA_GAME_ID
    ra_hashes = RA_HASHES
    REQUIRED_DECOMP_FILES = (
        Path("src/data/wild_encounters.json"),
        Path("data/maps/map_groups.json"),
        Path("include/constants/pokedex.h"),
        Path("include/constants/species.h"),
        Path("include/constants/flags.h"),
        Path("include/constants/opponents.h"),
        Path("src/data/pokemon/species_info.h"),
        Path("src/battle_setup.c"),
        Path("include/constants/metatile_behaviors.h"),
        Path("src/metatile_behavior.c"),
        Path("data/tilesets/primary/general/metatile_attributes.bin"),
        Path("data/tilesets/secondary/fortree/metatile_attributes.bin"),
        Path("data/layouts/Route119/map.bin"),
    )

    def __init__(
        self,
        pokeemerald_root: Path,
        account_progress: RAProgress | None = None,
        state_directory: Path | None = None,
        map_catalog: EmeraldMapCatalog | None = None,
        map_document: MapDocument | None = None,
        icon_renderer=None,
        icon_cache_directory: Path | None = None,
    ) -> None:
        self._validate_decomp_root(pokeemerald_root)
        self._account_progress = account_progress
        self._map_catalog = map_catalog
        self._map_document = map_document
        self._map_overlays = (
            EmeraldOverlayBuilder(map_catalog) if map_catalog is not None else None
        )
        self._region_sections: dict = {}
        self._section_positions: dict = {}
        self._section_groups: dict = {}
        if map_catalog is not None:
            try:
                self._region_sections = load_region_sections(pokeemerald_root)
                self._section_positions = section_positions(
                    parse_region_layout(pokeemerald_root), self._region_sections
                )
            except (OSError, ValueError):
                self._region_sections = {}
                self._section_positions = {}
            for entry in map_catalog.entries:
                if entry.region_section:
                    self._section_groups.setdefault(
                        entry.region_section, []
                    ).append(entry)
        self._world_cache_key: tuple = ()
        self._world_cache: tuple = ()
        self._training_tracker = TrainingAreaTracker(state_directory)
        self._battle_tracker = BattleParticipationTracker()
        self._hunt_tracker = HuntTracker(state_directory)
        self._journal = SessionJournal(state_directory)
        self._training_cache_path: Path | None = None
        self._player_trainer_id = 0
        self._current_party: tuple[PokemonState, ...] = ()

        knowledge = EmeraldKnowledge.load(
            Path(__file__).resolve().parent / "data" / "emerald_knowledge.json"
        )
        self._knowledge = knowledge
        group = knowledge["encounter_group"]
        group_document = knowledge["map_groups"]
        self._field_definitions = {
            field["type"]: field for field in group["fields"]
        }
        self._encounters = {
            entry["map"]: entry for entry in group["encounters"]
        }
        self._national_dex_numbers = {
            name: int(value) for name, value in knowledge["national_dex"].items()
        }
        self._species_ids = {
            name: int(value) for name, value in knowledge["species_ids"].items()
        }
        self._species_by_id = {
            value: name for name, value in self._species_ids.items()
        }
        self._species_info = knowledge["species"]
        self._catch_rates = {
            name: int(values["catch_rate"])
            for name, values in self._species_info.items()
        }
        self._exp_yields = {
            name: int(values["exp_yield"])
            for name, values in self._species_info.items()
        }
        self._growth_rates = {
            name: str(values["growth_rate"])
            for name, values in self._species_info.items()
        }
        self._flag_ids = {
            name: int(value) for name, value in knowledge["flag_ids"].items()
        }
        self._trainer_ids = {
            name: int(value) for name, value in knowledge["trainer_ids"].items()
        }
        variable_ids = {
            name: int(value)
            for name, value in knowledge["variable_ids"].items()
        }
        self._item_names = {
            int(item_id): str(name)
            for item_id, name in knowledge["items"].items()
        }
        self._move_info = {
            int(move_id): values
            for move_id, values in knowledge["moves"].items()
        }
        self._ability_names = {
            int(ability_id): str(name)
            for ability_id, name in knowledge["abilities"].items()
        }
        self._trainer_info = {
            int(trainer_id): values
            for trainer_id, values in knowledge["trainers"].items()
        }
        self._map_names_by_id = self._build_map_names(group_document)
        self._map_constants_by_id = self._build_map_constants(group_document)
        self.map_ids = self._build_map_ids(group_document, self._encounters)
        self._encounters_by_id = {
            self.map_ids[map_name]: encounter
            for map_name, encounter in self._encounters.items()
        }
        self._route_trackers = {
            map_name: (
                {
                    name: tuple(int(value) for value in ids)
                    for name, ids in values["trainer_groups"].items()
                },
                {
                    name: int(value)
                    for name, value in values["item_flags"].items()
                },
                {
                    name: int(value)
                    for name, value in values["objective_flags"].items()
                },
            )
            for map_name, values in knowledge["route_trackers"].items()
        }
        self._item_locations = {
            map_name: tuple(tuple(row) for row in rows)
            for map_name, rows in knowledge["item_locations"].items()
        }
        self._rematches_by_map = {
            map_name: tuple((int(index), str(name)) for index, name in rows)
            for map_name, rows in knowledge["rematches"].items()
        }
        self._route119_fishing_spots = {
            tuple(int(value) for value in coordinates.split(",")): int(spot)
            for coordinates, spot in knowledge[
                "route119_fishing_spots"
            ].items()
        }

        type_chart_rows = tuple(
            tuple(int(value) for value in row)
            for row in knowledge["type_chart"]
        )
        self._variable_ids = variable_ids
        self._icon_cache = SpeciesIconCache(
            pokeemerald_root,
            icon_cache_directory or state_directory,
            icon_renderer,
        )
        self._presenter = EmeraldPresenter(
            self._species_info,
            self._item_names,
            self._move_info,
            self._ability_names,
            type_chart_rows,
            icon_for=self._icon_cache.path_for,
        )
        self._poc_planner = PocPlanner(
            knowledge.document, self._national_dex_numbers
        )
        self._wild_scout = WildScout(build_family_map(knowledge["evolutions"]))
        self._battle_builder = BattleSnapshotBuilder(
            self._species_by_id,
            self._national_dex_numbers,
            self._catch_rates,
            self._presenter,
            self._battle_tracker,
            self.DISPLAY_SPEC,
            hunt=self._hunt_tracker,
            wild_scout=self._wild_scout,
        )
        self._event_detector = EventDetector(
            {
                number: name
                for name, number in self._national_dex_numbers.items()
            },
            self._flag_ids,
        )
        self._pickup_watcher = PickupWatcher(
            self._species_info, self._item_names
        )
        self._matchcall = MatchCallDashboard(self._rematches_by_map)
        self._factory_advisor = FactoryAdvisor(
            knowledge["frontier_mons"],
            self._species_info,
            self._move_info,
            self._item_names,
            type_chart_rows,
        )
        self._navigator = ObjectiveNavigator(
            self._flag_ids, knowledge["map_connections"]
        )
        self._legendary_dashboard = LegendaryDashboard(
            self._flag_ids, self._national_dex_numbers
        )
        self._rtc_dashboard = RtcEventDashboard(
            self._flag_ids,
            variable_ids,
            self._species_by_id,
            self._item_names,
            self._map_names_by_id,
        )
        self._daycare_dashboard = DaycareDashboard(
            self._species_by_id, self._species_info, self._flag_ids
        )
        self._frontier_dashboard = BattleFrontierDashboard(
            self._flag_ids, variable_ids, self._factory_advisor
        )
        self._overworld = OverworldPresenter(
            account_progress=account_progress,
            field_definitions=self._field_definitions,
            national_dex=self._national_dex_numbers,
            species_by_id=self._species_by_id,
            flag_ids=self._flag_ids,
            route_trackers=self._route_trackers,
            item_locations=self._item_locations,
            rematches=self._rematches_by_map,
            fishing_spots=self._route119_fishing_spots,
            exp_yields=self._exp_yields,
            growth_rates=self._growth_rates,
            training_tracker=self._training_tracker,
            poc_planner=self._poc_planner,
        )

    def activate(self, _content_key: tuple[str, str, str]) -> None:
        self.reset_session()

    def deactivate(self) -> None:
        self.reset_session()

    def reset_session(self) -> None:
        self._world_cache_key = ()
        self._world_cache = ()
        self._battle_tracker.end()
        self._battle_builder.reset_session()
        self._training_tracker.reset_session()
        self._hunt_tracker.reset_session()
        self._journal.reset_session()
        self._event_detector.reset_session()
        self._pickup_watcher.reset_session()
        self._training_cache_path = None
        self._player_trainer_id = 0
        self._current_party = ()

    def supports(
        self, status: RetroArchStatus, content_hash: str | None = None
    ) -> bool:
        core = status.core.casefold()
        if core not in {"mgba", "game_boy_advance"}:
            return False
        if content_hash is not None:
            return content_hash.casefold() in self.ra_hashes
        return "emerald" in status.content.casefold()

    def snapshot(self, memory: MemoryReader) -> OverlaySnapshot:
        pointer = int.from_bytes(
            memory.read_memory(SAVE_BLOCK_1_POINTER, 4), "little"
        )
        if pointer == 0:
            self.reset_session()
            return OverlaySnapshot(
                self.name,
                "Waiting for game/save",
                (
                    PanelSection(
                        "Status",
                        (PanelRow("Load or continue a save"),),
                        role="goals",
                        key="status",
                    ),
                ),
                supports_caught_filter=True,
                display_spec=self.DISPLAY_SPEC,
            )
        if not EWRAM_START <= pointer < EWRAM_END:
            raise RetroArchError(
                f"Invalid Emerald save block pointer: 0x{pointer:08X}"
            )
        save_block_2 = self._save_block_2_pointer(memory)
        pointers = SavePointers(pointer, save_block_2)
        self._select_player_context(memory, save_block_2)
        result = self._snapshot(memory, pointer, save_block_2)
        try:
            verify_save_pointers(memory, pointers)
        except RetroArchError:
            # CB2_InitBattle() calls MoveSaveBlocks_ResetHeap(), so Emerald
            # relocates SaveBlock1/2 on every battle entry. That is a legitimate
            # move, not a torn read: rebuild once against the new pointers.
            pointer = int.from_bytes(
                memory.read_memory(SAVE_BLOCK_1_POINTER, 4), "little"
            )
            if not EWRAM_START <= pointer < EWRAM_END:
                raise
            save_block_2 = self._save_block_2_pointer(memory)
            pointers = SavePointers(pointer, save_block_2)
            self._select_player_context(memory, save_block_2)
            result = self._snapshot(memory, pointer, save_block_2)
            verify_save_pointers(memory, pointers)
        return result

    def _select_player_context(
        self,
        memory: MemoryReader,
        save_block_2: int,
    ) -> None:
        trainer_id = memory.read_memory(save_block_2 + 0x0A, 4)
        if len(trainer_id) != 4:
            raise RetroArchError("Emerald Trainer ID read was incomplete")
        self._player_trainer_id = int.from_bytes(trainer_id, "little")
        self._training_tracker.select_playthrough(self._player_trainer_id)
        self._hunt_tracker.select_playthrough(self._player_trainer_id)
        self._journal.select_playthrough(self._player_trainer_id)
        self._training_cache_path = self._training_tracker.path

    def _snapshot(
        self, memory: MemoryReader, save_block_1: int, save_block_2: int
    ) -> OverlaySnapshot:
        map_data = memory.read_memory(save_block_1 + 4, 2)
        if len(map_data) != 2:
            raise RetroArchError("Emerald map location read was incomplete")
        map_group, map_number = map_data
        party_error = self._read_party_safely(memory)
        caught_flags = memory.read_memory(
            save_block_2 + POKEDEX_OWNED_OFFSET, DEX_FLAG_BYTES
        )
        if len(caught_flags) != DEX_FLAG_BYTES:
            raise RetroArchError("Emerald Pokedex read was incomplete")
        map_name = self._map_constants_by_id.get((map_group, map_number), "")
        location = self._map_names_by_id.get(
            (map_group, map_number), f"Map {map_group}:{map_number}"
        )
        event_flags = memory.read_memory(
            save_block_1 + FLAGS_OFFSET, FLAGS_SIZE
        )
        if len(event_flags) != FLAGS_SIZE:
            raise RetroArchError("Emerald progression read was incomplete")
        self._record_journal_events(caught_flags, event_flags)
        map_position = self._map_position(memory, save_block_1, map_group, map_number)
        map_overlays = self._map_marker_overlays(
            memory, save_block_1, map_group, map_number, event_flags, caught_flags
        )
        battle = self._battle_builder.snapshot(
            memory,
            save_block_1,
            save_block_2,
            caught_flags,
            map_name,
            location,
            self._current_party,
        )
        if battle is not None:
            return replace(
                battle,
                map_position=map_position,
                map_document=self._map_document,
                map_overlays=map_overlays,
            )

        rematches = memory.read_memory(
            save_block_1 + REMATCHES_OFFSET, REMATCHES_SIZE
        )
        if len(rematches) != REMATCHES_SIZE:
            raise RetroArchError("Emerald progression read was incomplete")
        encounter = self._encounters_by_id.get((map_group, map_number))
        sections = self._base_overworld_sections(
            memory,
            save_block_1,
            save_block_2,
            map_group,
            map_number,
            map_name,
            location,
            event_flags,
            caught_flags,
            rematches,
            encounter,
            party_error,
        )
        if encounter is not None:
            for field_name, title, section_key in (
                ("land_mons", "Land", "encounters-land"),
                ("water_mons", "Water", "encounters-water"),
                ("rock_smash_mons", "Rock Smash", "encounters-rock-smash"),
            ):
                if field_name in encounter:
                    sections.append(
                        self._overworld.encounter_section(
                            title,
                            section_key,
                            field_name,
                            encounter[field_name],
                            caught_flags,
                        )
                    )
            fishing = encounter.get("fishing_mons")
            if fishing:
                definition = self._field_definitions["fishing_mons"]
                for rod_name, indexes in definition["groups"].items():
                    sections.append(
                        self._overworld.encounter_section(
                            _display_constant(rod_name.upper(), ""),
                            f"encounters-{rod_name.casefold().replace('_', '-')}",
                            "fishing_mons",
                            fishing,
                            caught_flags,
                            indexes,
                        )
                    )
            location = _display_constant(encounter["map"], "MAP_")
        for title, section_key, builder in (
            (
                "Repel planner",
            "repel-planner",
                lambda: repel_section(
                    self._field_definitions,
                    encounter,
                    self._current_party,
                    self._repel_steps(memory, save_block_1),
                    _display_constant,
                )
                if encounter is not None
                else None,
            ),
            ("Hunt stats", "hunt-stats", lambda: self._hunt_section(encounter)),
            (
                "Pickup",
                "pickup",
                lambda: self._pickup_watcher.section(self._current_party),
            ),
            ("Match Call", "match-call", lambda: self._matchcall.section(rematches)),
            ("Journal", "journal", self._journal.section),
        ):
            section = self._safe_optional_section(title, section_key, builder)
            if section is not None:
                sections.append(section)
        sections.append(
            self._overworld.collection_section(
                memory, save_block_1, event_flags
            )
        )
        return OverlaySnapshot(
            self.name,
            location,
            tuple(sections),
            map_position=map_position,
            supports_caught_filter=True,
            map_document=self._map_document,
            map_overlays=map_overlays,
            display_spec=self.DISPLAY_SPEC,
        )

    def _map_position(
        self,
        memory: MemoryReader,
        save_block_1: int,
        map_group: int,
        map_number: int,
    ) -> MapPosition | None:
        if self._map_catalog is None:
            return None
        entry = self._map_catalog.entry(map_group, map_number)
        if entry is None:
            return None
        try:
            position = memory.read_memory(save_block_1 + PLAYER_POS_OFFSET, 4)
        except (RetroArchError, ValueError):
            return None
        if len(position) != 4:
            return None
        # SaveBlock1.pos already holds border-free map coordinates, unlike the
        # gObjectEvents coordinates which include the 7-tile border.
        x = int.from_bytes(position[0:2], "little", signed=True)
        y = int.from_bytes(position[2:4], "little", signed=True)
        layout = self._map_catalog.layout(entry.layout_id)
        if layout is not None and not (
            0 <= x < layout.width and 0 <= y < layout.height
        ):
            # Out-of-range coordinates would wrap to the far edge of the map.
            return None
        return MapPosition("Hoenn", entry.numeric_id, x, y)

    def _map_marker_overlays(
        self,
        memory: MemoryReader,
        save_block_1: int,
        map_group: int,
        map_number: int,
        event_flags: bytes,
        caught_flags: bytes = b"",
    ) -> tuple:
        if self._map_overlays is None or self._map_catalog is None:
            return ()
        entry = self._map_catalog.entry(map_group, map_number)
        feebas: tuple = ()
        key = ""
        if entry is not None and entry.name == FEEBAS_MAP_NAME:
            try:
                seed = int.from_bytes(
                    memory.read_memory(
                        save_block_1 + DEWFORD_TREND_SEED_OFFSET, 2
                    ),
                    "little",
                )
            except (RetroArchError, ValueError):
                seed = None
            if seed is not None:
                key = entry.key
                feebas = feebas_waypoints(
                    self._overworld.fishing_spots, feebas_spot_ids(seed)
                )
        overlays = self._map_overlays.overlays(event_flags, feebas, key)
        world = self._world_overlay(event_flags, caught_flags)
        return overlays + world if world else overlays

    def _world_overlay(self, event_flags: bytes, caught_flags: bytes) -> tuple:
        if not self._region_sections or not self._section_groups:
            return ()
        key = (
            blake2b(event_flags, digest_size=8).digest(),
            blake2b(caught_flags, digest_size=8).digest(),
        )
        if key != self._world_cache_key:
            waypoints = world_waypoints(
                self._region_sections,
                self._section_groups,
                event_flags,
                caught_flags,
                self._encounters,
                self._field_definitions,
                self._overworld.encounter_species,
                self._overworld.is_caught,
                self._section_positions,
                self._map_catalog.section_parents if self._map_catalog else {},
            )
            self._world_cache_key = key
            self._world_cache = (MapOverlay("hoenn", waypoints),) if waypoints else ()
        return self._world_cache

    def _base_overworld_sections(
        self,
        memory: MemoryReader,
        save_block_1: int,
        save_block_2: int,
        map_group: int,
        map_number: int,
        map_name: str,
        location: str,
        event_flags: bytes,
        caught_flags: bytes,
        rematches: bytes,
        encounter: dict[str, Any] | None,
        party_error: str,
    ) -> list[PanelSection]:
        sections = []
        for section in (
            self._overworld.missable_section(map_name, event_flags),
            self._overworld.poc_section(
                caught_flags,
                event_flags,
                encounter,
                location,
                self._current_party,
            ),
            self._overworld.achievement_section(),
            self._overworld.roamer_section(
                memory, save_block_1, map_group, map_number
            )
            if encounter is not None
            else None,
            self._overworld.feebas_section(memory, save_block_1, map_name)
            if encounter is not None
            else None,
            self._overworld.nearby_achievement_section(
                map_name, event_flags
            ),
        ):
            if section is not None:
                sections.append(section)
        sections.extend(
            self._supplemental_sections(
                memory,
                save_block_1,
                save_block_2,
                map_name,
                event_flags,
                caught_flags,
                party_error,
            )
        )
        sections.extend(
            self._overworld.completion_sections(
                memory,
                save_block_1,
                map_name,
                event_flags,
                rematches,
            )
        )
        return sections

    def _supplemental_sections(
        self,
        memory: MemoryReader,
        save_block_1: int,
        save_block_2: int,
        map_name: str,
        event_flags: bytes,
        caught_flags: bytes,
        party_error: str,
    ) -> tuple[PanelSection, ...]:
        builders: tuple[
            tuple[str, str, Callable[[], PanelSection | None]], ...
        ] = (
            (
                "Navigator",
                "navigator",
                lambda: self._navigator.section(map_name, event_flags),
            ),
            (
                "Vanilla legendaries",
                "legendaries",
                lambda: self._legendary_dashboard.section(
                    event_flags,
                    caught_flags,
                    memory.read_memory(
                        save_block_1 + ROAMER_OFFSET, ROAMER_SIZE
                    ),
                ),
            ),
            (
                "World events",
                "world-events",
                lambda: self._rtc_dashboard.section(
                    memory,
                    save_block_1,
                    save_block_2,
                    event_flags,
                    self._current_party,
                ),
            ),
            (
                "Daycare & eggs",
                "daycare",
                lambda: self._daycare_dashboard.section(
                    memory,
                    save_block_1,
                    event_flags,
                    self._current_party,
                ),
            ),
            (
                "Battle Frontier",
                "frontier",
                lambda: self._frontier_dashboard.section(
                    memory,
                    save_block_1,
                    save_block_2,
                    event_flags,
                ),
            ),
        )
        sections = []
        for title, section_key, builder in builders:
            section = self._safe_optional_section(title, section_key, builder)
            if section is not None:
                sections.append(section)
        if party_error:
            sections.append(
                PanelSection(
                    "Party unavailable",
                    (PanelRow(party_error),),
                    priority=90,
                    role="party",
                    key="party",
                )
            )
        else:
            try:
                sections.extend(
                    self._party_presentations(memory, save_block_1)
                )
            except (
                OSError,
                RetroArchError,
                ValueError,
                KeyError,
                IndexError,
                TypeError,
            ) as error:
                LOGGER.exception("Pokemon Emerald party presentation failed")
                sections.append(
                    PanelSection(
                        "Party details unavailable",
                        (PanelRow(str(error)),),
                        priority=90,
                        role="party",
                        key="party",
                    )
                )
        return tuple(sections)

    def _record_journal_events(
        self, caught_flags: bytes, event_flags: bytes
    ) -> None:
        identity = f"{self._player_trainer_id:08x}"
        try:
            events = self._event_detector.observe(
                identity, caught_flags, event_flags, self._current_party
            )
            events.extend(
                ("pickup", text)
                for text in self._pickup_watcher.observe(
                    identity, self._current_party
                )
            )
            for kind, text in events:
                self._journal.record(kind, text)
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            LOGGER.exception("Pokemon Emerald journal detection failed")

    def _repel_steps(self, memory: MemoryReader, save_block_1: int) -> int:
        variable_id = self._variable_ids.get("VAR_REPEL_STEP_COUNT")
        if variable_id is None:
            return 0
        data = memory.read_memory(
            save_block_1 + VARS_OFFSET + (variable_id - VARS_START) * 2, 2
        )
        return int.from_bytes(data, "little") if len(data) == 2 else 0

    def _hunt_section(self, encounter: dict[str, Any] | None) -> PanelSection | None:
        session = self._hunt_tracker.session
        if not session:
            return None
        rows = []
        for species, count in sorted(session.items(), key=lambda item: -item[1]):
            stats = self._hunt_tracker.stats_for(species) or {}
            rows.append(
                PanelRow(
                    f"{_display_constant(species, 'SPECIES_')} · {count} this "
                    f"session · lifetime {stats.get('seen', 0)} seen · "
                    f"{stats.get('caught', 0)} caught · {stats.get('ko', 0)} KO "
                    f"· {stats.get('fled', 0)} fled",
                    icon=self._icon_cache.path_for(species),
                )
            )
        total = sum(session.values())
        return PanelSection(
            f"Hunt stats · {total} this session",
            tuple(rows),
            preview_limit=4,
            priority=18,
            role="area",
            compact_rows=(PanelRow(f"{total} wild battles this session"),),
            key="hunt-stats",
        )

    def _read_party_safely(self, memory: MemoryReader) -> str:
        try:
            count_data = memory.read_memory(PLAYER_PARTY_COUNT_ADDRESS, 1)
            if len(count_data) != 1:
                raise RetroArchError("Emerald party count read was incomplete")
            count = min(count_data[0], PARTY_SIZE)
            data = memory.read_memory(
                PLAYER_PARTY_ADDRESS, POKEMON_SIZE * count
            )
            self._current_party = decode_party(
                data,
                count,
                self._species_by_id,
                player_trainer_id=self._player_trainer_id,
            )
            return ""
        except (
            OSError,
            RetroArchError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as error:
            LOGGER.exception("Pokemon Emerald party state is unavailable")
            self._current_party = ()
            return str(error)

    def _party_presentations(
        self, memory: MemoryReader, save_block_1: int
    ) -> tuple[PanelSection, ...]:
        pokeblocks = decode_pokeblocks(
            memory.read_memory(
                save_block_1 + POKEBLOCKS_OFFSET, POKEBLOCKS_SIZE
            )
        )
        sections = (
            self._presenter.party_section(self._current_party),
            self._presenter.contest_section(
                self._current_party, pokeblocks
            ),
        )
        return tuple(section for section in sections if section is not None)

    @staticmethod
    def _safe_optional_section(
        title: str,
        key: str,
        builder: Callable[[], PanelSection | None],
    ) -> PanelSection | None:
        try:
            return builder()
        except (
            OSError,
            RetroArchError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as error:
            LOGGER.exception("Pokemon Emerald feature %s failed", title)
            return PanelSection(
                f"{title} unavailable",
                (PanelRow(str(error)),),
                priority=95,
                role="goals",
                key=key,
            )

    @classmethod
    def _validate_decomp_root(cls, pokeemerald_root: Path) -> None:
        missing = [
            path
            for path in cls.REQUIRED_DECOMP_FILES
            if not (pokeemerald_root / path).exists()
        ]
        if missing:
            details = ", ".join(
                str(path).replace("\\", "/") for path in missing[:4]
            )
            if len(missing) > 4:
                details += f", and {len(missing) - 4} more"
            raise FileNotFoundError(
                "Pokémon Emerald support requires a pokeemerald decomp checkout. "
                f"Expected it at {pokeemerald_root}. Missing: {details}. "
                "Run git submodule update --init --recursive in the plugin repository."
            )

    @staticmethod
    def _save_block_2_pointer(memory: MemoryReader) -> int:
        pointer = int.from_bytes(
            memory.read_memory(SAVE_BLOCK_2_POINTER, 4), "little"
        )
        if not EWRAM_START <= pointer < EWRAM_END:
            raise RetroArchError(
                f"Invalid Emerald save block 2 pointer: 0x{pointer:08X}"
            )
        return pointer

    @staticmethod
    def _build_map_names(
        document: dict[str, Any]
    ) -> dict[tuple[int, int], str]:
        return {
            (group_number, map_number): _display_map_name(map_name)
            for group_number, group_name in enumerate(document["group_order"])
            for map_number, map_name in enumerate(document[group_name])
        }

    @staticmethod
    def _build_map_constants(
        document: dict[str, Any]
    ) -> dict[tuple[int, int], str]:
        return {
            (group_number, map_number): map_name
            for group_number, group_name in enumerate(document["group_order"])
            for map_number, map_name in enumerate(document[group_name])
        }

    @staticmethod
    def _build_map_ids(
        document: dict[str, Any], encounter_names: dict[str, Any]
    ) -> dict[str, tuple[int, int]]:
        normalized: dict[str, tuple[int, int]] = {}
        for group_number, group_name in enumerate(document["group_order"]):
            for map_number, map_name in enumerate(document[group_name]):
                normalized[_normalize_map_name(map_name)] = (
                    group_number,
                    map_number,
                )
        return {
            map_name: normalized[_normalize_map_name(map_name)]
            for map_name in encounter_names
            if _normalize_map_name(map_name) in normalized
        }