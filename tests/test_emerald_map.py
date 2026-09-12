import tempfile
import unittest
from pathlib import Path

from PIL import Image

from game.mapdata import (
    KIND_BERRY,
    KIND_HIDDEN,
    KIND_ITEM,
    KIND_REMATCH,
    KIND_TRAINER,
    TRAINER_FLAGS_START,
    EmeraldMapCatalog,
    EmeraldMapEntry,
    parse_defines,
    parse_rematch_trainers,
    parse_script_bindings,
)
from game.mapoverlays import EmeraldOverlayBuilder, feebas_waypoints, flag_is_set
from map_renderer import Tileset, render_layout


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POKEEMERALD_ROOT = PROJECT_ROOT / "decomp_reference" / "pokeemerald"
requires_pokeemerald = unittest.skipUnless(
    (POKEEMERALD_ROOT / "data" / "maps" / "map_groups.json").is_file(),
    "pokeemerald decomp checkout is not available",
)


def solid_tileset(color: tuple[int, int, int]) -> Tileset:
    """A tileset whose bottom layer is one opaque color and top layer is clear."""
    opaque = bytes([1] * 64)
    blank = bytes(64)
    metatile = bytearray()
    for slot in range(8):
        metatile += (0 if slot < 4 else 1).to_bytes(2, "little")
    palette = ((0, 0, 0), color) + ((0, 0, 0),) * 14
    return Tileset((opaque, blank), bytes(metatile), bytes(2), (palette,) * 16)


class MapRendererTests(unittest.TestCase):
    def test_layout_renders_one_metatile_per_block(self) -> None:
        tileset = solid_tileset((10, 20, 30))
        with tempfile.TemporaryDirectory() as directory:
            path = render_layout(
                bytes(4), 2, 1, tileset, tileset, Path(directory) / "map.png"
            )
            with Image.open(path) as image:
                self.assertEqual(image.size, (32, 16))
                self.assertEqual(image.getpixel((0, 0)), (10, 20, 30))
                self.assertEqual(image.getpixel((31, 15)), (10, 20, 30))

    def test_short_blockdata_is_rejected(self) -> None:
        tileset = solid_tileset((1, 2, 3))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                render_layout(
                    bytes(2), 4, 4, tileset, tileset, Path(directory) / "map.png"
                )

    def test_empty_layout_is_rejected(self) -> None:
        tileset = solid_tileset((1, 2, 3))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                render_layout(
                    b"", 0, 0, tileset, tileset, Path(directory) / "map.png"
                )


class DefineParsingTests(unittest.TestCase):
    def test_plain_and_additive_defines_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            header = Path(directory) / "flags.h"
            header.write_text(
                "#define BASE 0x1F4\n"
                "#define OFFSET_ONE (BASE + 0x05)\n"
                "#define PLAIN 12\n",
                encoding="utf-8",
            )
            defines = parse_defines(header)
        self.assertEqual(defines["BASE"], 0x1F4)
        self.assertEqual(defines["OFFSET_ONE"], 0x1F9)
        self.assertEqual(defines["PLAIN"], 12)

    def test_bare_trainerbattle_skips_the_battle_type_constant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "scripts.inc"
            script.write_text(
                "Gym_EventScript_Cole::\n"
                "\ttrainerbattle TRAINER_BATTLE_CONTINUE_SCRIPT, TRAINER_COLE, 0, Text\n"
                "\tend\n"
                "Route_EventScript_Item::\n"
                "\tfinditem ITEM_NUGGET\n"
                "\tend\n",
                encoding="utf-8",
            )
            trainers, items = parse_script_bindings(script)
        self.assertEqual(trainers["Gym_EventScript_Cole"], "TRAINER_COLE")
        self.assertEqual(items["Route_EventScript_Item"], "ITEM_NUGGET")

    def test_single_trainerbattle_binds_the_named_opponent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "scripts.inc"
            script.write_text(
                "Route119_EventScript_Greg::\n"
                "\ttrainerbattle_single TRAINER_GREG, Intro, Defeat\n"
                "\tend\n",
                encoding="utf-8",
            )
            trainers, _ = parse_script_bindings(script)
        self.assertEqual(trainers["Route119_EventScript_Greg"], "TRAINER_GREG")


class FlagTests(unittest.TestCase):
    def test_flag_bits_are_indexed_within_each_byte(self) -> None:
        flags = bytes([0b0000_0101])
        self.assertTrue(flag_is_set(flags, 0))
        self.assertFalse(flag_is_set(flags, 1))
        self.assertTrue(flag_is_set(flags, 2))

    def test_out_of_range_flag_is_not_set(self) -> None:
        self.assertFalse(flag_is_set(b"\xff", 64))


class FeebasWaypointTests(unittest.TestCase):
    def test_only_active_spots_become_waypoints(self) -> None:
        spots = {(1, 1): 10, (2, 2): 11, (3, 3): 12}
        waypoints = feebas_waypoints(spots, (10, 12))
        self.assertEqual([(point.x, point.y) for point in waypoints], [(1, 1), (3, 3)])
        self.assertTrue(all(point.kind == "feebas" for point in waypoints))


@requires_pokeemerald
class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = EmeraldMapCatalog(POKEEMERALD_ROOT)

    def test_route119_is_indexed_by_group_and_number(self) -> None:
        entry = self.catalog.entry(0, 34)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.map_id, "MAP_ROUTE119")
        self.assertEqual(entry.key, "route119")
        self.assertEqual(entry.numeric_id, 34)

    def test_route119_carries_every_static_marker_kind(self) -> None:
        kinds = {marker.kind for marker in self.catalog.entry(0, 34).markers}
        self.assertEqual(
            kinds, {KIND_TRAINER, KIND_REMATCH, KIND_ITEM, KIND_HIDDEN, KIND_BERRY}
        )

    def test_trainer_flag_is_offset_from_the_trainer_id(self) -> None:
        greg = next(
            marker
            for marker in self.catalog.entry(0, 34).markers
            if marker.title == "Greg"
        )
        self.assertEqual(greg.flag, TRAINER_FLAGS_START + 619)

    def test_every_trainer_marker_resolves_a_flag(self) -> None:
        unresolved = [
            (entry.name, marker.title)
            for entry in self.catalog.entries
            for marker in entry.markers
            if marker.kind in {KIND_TRAINER, KIND_REMATCH} and marker.flag is None
        ]
        self.assertEqual(unresolved, [])

    def test_rematch_ladder_is_recorded_in_the_detail(self) -> None:
        rematch = next(
            marker
            for marker in self.catalog.entry(0, 34).markers
            if marker.kind == KIND_REMATCH
        )
        self.assertIn("Rebattlable", rematch.detail)
        self.assertIn("->", rematch.detail)

    def test_single_battle_trainers_are_not_marked_rebattlable(self) -> None:
        greg = next(
            marker
            for marker in self.catalog.entry(0, 34).markers
            if marker.title == "Greg"
        )
        self.assertEqual(greg.kind, KIND_TRAINER)
        self.assertEqual(greg.detail, "Single battle only")

    def test_hidden_items_are_separated_from_visible_item_balls(self) -> None:
        markers = self.catalog.entry(0, 34).markers
        hidden = [marker for marker in markers if marker.kind == KIND_HIDDEN]
        visible = [marker for marker in markers if marker.kind == KIND_ITEM]
        self.assertTrue(hidden)
        self.assertTrue(visible)
        self.assertTrue(all(marker.marker == "quest" for marker in hidden))
        self.assertTrue(all(marker.marker == "item" for marker in visible))

    def test_rematch_ladders_start_at_the_first_battle(self) -> None:
        ladders = parse_rematch_trainers(POKEEMERALD_ROOT / "src" / "battle_setup.c")
        self.assertEqual(
            ladders["TRAINER_ROSE_1"][:2], ("TRAINER_ROSE_1", "TRAINER_ROSE_2")
        )


@requires_pokeemerald
class OverlayBuilderTests(unittest.TestCase):
    GREG_FLAG = TRAINER_FLAGS_START + 619

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = EmeraldMapCatalog(POKEEMERALD_ROOT)

    def flags(self, *set_flags: int) -> bytes:
        flags = bytearray(0x160)
        for flag in set_flags:
            flags[flag // 8] |= 1 << (flag % 8)
        return bytes(flags)

    def route119(self, overlays) -> tuple:
        return next(
            overlay.waypoints
            for overlay in overlays
            if overlay.layer_key == "route119"
        )

    def test_set_flag_marks_the_marker_completed(self) -> None:
        builder = EmeraldOverlayBuilder(self.catalog)
        waypoints = self.route119(builder.overlays(self.flags(self.GREG_FLAG)))
        greg = next(point for point in waypoints if point.title == "Greg")
        self.assertTrue(greg.completed)
        self.assertIn("Defeated", greg.detail)

    def test_clear_flag_leaves_the_marker_pending(self) -> None:
        builder = EmeraldOverlayBuilder(self.catalog)
        waypoints = self.route119(builder.overlays(self.flags()))
        greg = next(point for point in waypoints if point.title == "Greg")
        self.assertFalse(greg.completed)
        self.assertIn("Not yet battled", greg.detail)

    def test_identical_flags_reuse_the_cached_overlays(self) -> None:
        builder = EmeraldOverlayBuilder(self.catalog)
        first = builder.overlays(self.flags(self.GREG_FLAG))
        self.assertIs(first, builder.overlays(self.flags(self.GREG_FLAG)))
        self.assertIsNot(first, builder.overlays(self.flags(self.GREG_FLAG + 1)))

    def test_feebas_waypoints_merge_into_the_route_overlay(self) -> None:
        builder = EmeraldOverlayBuilder(self.catalog)
        base = len(self.route119(builder.overlays(self.flags())))
        extra = feebas_waypoints({(5, 5): 7}, (7,))
        merged = self.route119(builder.overlays(self.flags(), extra, "route119"))
        self.assertEqual(len(merged), base + 1)
        self.assertEqual(merged[-1].kind, "feebas")

    def test_feebas_waypoints_are_ignored_without_a_layer_key(self) -> None:
        builder = EmeraldOverlayBuilder(self.catalog)
        base = len(self.route119(builder.overlays(self.flags())))
        extra = feebas_waypoints({(5, 5): 7}, (7,))
        self.assertEqual(
            len(self.route119(builder.overlays(self.flags(), extra, ""))), base
        )


@requires_pokeemerald
class PrebuiltCatalogTests(unittest.TestCase):
    REVISION = "test-revision"

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = EmeraldMapCatalog(POKEEMERALD_ROOT)
        cls.document = cls.catalog.to_document(cls.REVISION)

    def test_round_trip_preserves_every_marker(self) -> None:
        restored = EmeraldMapCatalog.from_document(
            POKEEMERALD_ROOT, self.document, self.REVISION
        )
        self.assertEqual(len(restored.entries), len(self.catalog.entries))
        self.assertEqual(
            restored.entry(0, 34).markers, self.catalog.entry(0, 34).markers
        )

    def test_round_trip_preserves_layouts(self) -> None:
        restored = EmeraldMapCatalog.from_document(
            POKEEMERALD_ROOT, self.document, self.REVISION
        )
        self.assertEqual(
            restored.layout("LAYOUT_ROUTE119"),
            self.catalog.layout("LAYOUT_ROUTE119"),
        )

    def test_mismatched_revision_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EmeraldMapCatalog.from_document(
                POKEEMERALD_ROOT, self.document, "other-revision"
            )

    def test_mismatched_schema_is_rejected(self) -> None:
        stale = dict(self.document, schema_version=999)
        with self.assertRaises(ValueError):
            EmeraldMapCatalog.from_document(POKEEMERALD_ROOT, stale, self.REVISION)

    def test_missing_prebuilt_file_falls_back_to_the_decomp(self) -> None:
        from game.map_builder import load_map_catalog

        with tempfile.TemporaryDirectory() as directory:
            catalog = load_map_catalog(
                POKEEMERALD_ROOT, Path(directory) / "absent.json"
            )
        self.assertEqual(len(catalog.entries), len(self.catalog.entries))

    def test_shipped_map_data_matches_the_decomp(self) -> None:
        from game.map_builder import DEFAULT_OUTPUT, load_map_catalog

        if not DEFAULT_OUTPUT.is_file():
            self.skipTest("prebuilt emerald_map.json has not been generated")
        shipped = load_map_catalog(POKEEMERALD_ROOT, DEFAULT_OUTPUT)
        self.assertEqual(len(shipped.entries), len(self.catalog.entries))
        self.assertEqual(
            shipped.entry(0, 34).markers, self.catalog.entry(0, 34).markers
        )


@requires_pokeemerald
class BuildingRollupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = EmeraldMapCatalog(POKEEMERALD_ROOT)

    def buildings(self, map_id: str) -> list:
        entry = next(e for e in self.catalog.entries if e.map_id == map_id)
        return [m for m in entry.markers if m.kind == "buildings"]

    def test_town_shows_a_marker_for_a_building_that_gives_an_item(self) -> None:
        cut = next(
            m for m in self.buildings("MAP_RUSTBORO_CITY") if "Cutters" in m.title
        )
        self.assertIn("Hm Cut", cut.detail)
        self.assertEqual(cut.marker, "building")

    def test_town_shows_a_marker_for_an_in_game_trade(self) -> None:
        trade = next(
            m for m in self.buildings("MAP_RUSTBORO_CITY") if "House1" in m.title
        )
        self.assertIn("In-game trade", trade.detail)

    def test_buildings_without_anything_worth_visiting_are_skipped(self) -> None:
        titles = {m.title for m in self.buildings("MAP_RUSTBORO_CITY")}
        self.assertNotIn("Rustboro City Pokemon Center 1F", titles)

    def test_only_towns_and_cities_roll_up_their_interiors(self) -> None:
        for entry in self.catalog.entries:
            if any(m.kind == "buildings" for m in entry.markers):
                self.assertIn(entry.map_type, {"MAP_TYPE_TOWN", "MAP_TYPE_CITY"})


@requires_pokeemerald
class WorldMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from game.worldmap import load_region_sections

        cls.sections = load_region_sections(POKEEMERALD_ROOT)

    def test_region_sections_cover_hoenn(self) -> None:
        self.assertIn("MAPSEC_ROUTE_119", self.sections)
        littleroot = self.sections["MAPSEC_LITTLEROOT_TOWN"]
        self.assertEqual((littleroot.x, littleroot.y), (4, 11))

    def test_world_waypoint_counts_outstanding_work(self) -> None:
        from game.mapdata import MapMarker
        from game.worldmap import world_waypoints

        entry = EmeraldMapEntry(
            "MAP_TEST",
            "Test",
            0,
            0,
            "LAYOUT_TEST",
            (
                MapMarker(1, 1, KIND_ITEM, "item", "Potion", "", 10),
                MapMarker(2, 2, KIND_TRAINER, "person", "Rival", "", 11),
            ),
            "MAP_TYPE_ROUTE",
            "MAPSEC_LITTLEROOT_TOWN",
        )
        flags = bytearray(8)
        flags[11 // 8] |= 1 << (11 % 8)  # trainer already beaten
        points = world_waypoints(
            self.sections,
            {"MAPSEC_LITTLEROOT_TOWN": [entry]},
            bytes(flags),
            b"",
            {},
            {},
            lambda *_: {},
            lambda *_: True,
        )
        self.assertEqual(len(points), 1)
        self.assertIn("1 item left to collect", points[0].detail)
        self.assertNotIn("trainer", points[0].detail)
        self.assertFalse(points[0].completed)

    def test_section_with_nothing_left_is_marked_complete(self) -> None:
        from game.worldmap import world_waypoints

        entry = EmeraldMapEntry(
            "MAP_TEST", "Test", 0, 0, "LAYOUT_TEST", (), "MAP_TYPE_ROUTE",
            "MAPSEC_LITTLEROOT_TOWN",
        )
        points = world_waypoints(
            self.sections,
            {"MAPSEC_LITTLEROOT_TOWN": [entry]},
            b"\xff" * 8,
            b"",
            {},
            {},
            lambda *_: {},
            lambda *_: True,
        )
        self.assertTrue(points[0].completed)
        self.assertIn("Nothing left here", points[0].detail)

    def test_uncaught_species_are_labelled_by_method(self) -> None:
        from game.worldmap import uncaught_species

        encounter = {"land_mons": {"mons": []}, "fishing_mons": {"mons": []}}
        definitions = {"fishing_mons": {"groups": {"old_rod": [0, 1]}}}
        lines = uncaught_species(
            encounter,
            definitions,
            lambda field, data, indexes: {"SPECIES_ZIGZAGOON": {}},
            lambda name, flags: False,
            b"",
        )
        self.assertIn("Grass: Zigzagoon", lines)
        self.assertIn("Old Rod: Zigzagoon", lines)


@requires_pokeemerald
class RegionMarkerPlacementTests(unittest.TestCase):
    """Every region marker must sit on a cell its own section owns."""

    @classmethod
    def setUpClass(cls) -> None:
        from game.worldmap import (
            load_region_sections,
            parse_region_layout,
            section_positions,
        )

        cls.layout = parse_region_layout(POKEEMERALD_ROOT)
        cls.sections = load_region_sections(POKEEMERALD_ROOT)
        cls.positions = section_positions(cls.layout, cls.sections)

    def test_layout_is_the_documented_size(self) -> None:
        from game.worldmap import LAYOUT_COLS, LAYOUT_ROWS

        self.assertEqual(len(self.layout), LAYOUT_ROWS)
        self.assertTrue(all(len(row) == LAYOUT_COLS for row in self.layout))

    def test_every_section_marker_lands_on_its_own_cell(self) -> None:
        from game.worldmap import REGION_ORIGIN_X, REGION_ORIGIN_Y

        misplaced = []
        for section_id, (tile_x, tile_y) in self.positions.items():
            owner = self.layout[tile_y - REGION_ORIGIN_Y][tile_x - REGION_ORIGIN_X]
            if owner != section_id:
                misplaced.append((section_id, tile_x, tile_y, owner))
        self.assertEqual(misplaced, [])

    def test_every_marker_stays_inside_the_rendered_image(self) -> None:
        from game.worldmap import REGION_COLS, REGION_ROWS

        for section_id, (tile_x, tile_y) in self.positions.items():
            with self.subTest(section=section_id):
                self.assertTrue(0 <= tile_x < REGION_COLS)
                self.assertTrue(0 <= tile_y < REGION_ROWS)

    def test_only_sections_drawn_on_the_map_get_a_marker(self) -> None:
        drawn = {
            section
            for row in self.layout
            for section in row
            if section != "MAPSEC_NONE"
        }
        self.assertEqual(set(self.positions), drawn)

    def test_offstage_sections_roll_up_into_a_mapped_parent(self) -> None:
        catalog = EmeraldMapCatalog(POKEEMERALD_ROOT)
        parents = catalog.section_parents
        self.assertEqual(parents.get("MAPSEC_ABANDONED_SHIP"), "MAPSEC_ROUTE_108")
        self.assertEqual(
            parents.get("MAPSEC_CAVE_OF_ORIGIN"), "MAPSEC_SOOTOPOLIS_CITY"
        )
        for parent in parents.values():
            self.assertIn(parent, self.positions)

    def test_world_waypoints_drop_unplaceable_sections(self) -> None:
        from game.worldmap import world_waypoints

        entry = EmeraldMapEntry(
            "MAP_X", "X", 0, 0, "LAYOUT_X", (), "MAP_TYPE_ROUTE", "MAPSEC_DYNAMIC"
        )
        points = world_waypoints(
            self.sections,
            {"MAPSEC_DYNAMIC": [entry]},
            b"\x00" * 8,
            b"",
            {},
            {},
            lambda *_: {},
            lambda *_: True,
            self.positions,
            {},
        )
        self.assertEqual(points, ())


@requires_pokeemerald
class RegionMapRenderTests(unittest.TestCase):
    def test_region_map_renders_at_the_requested_scale(self) -> None:
        from map_renderer import REGION_COLS, REGION_ROWS, REGION_TILE, render_region_map

        with tempfile.TemporaryDirectory() as directory:
            path = render_region_map(
                POKEEMERALD_ROOT, Path(directory) / "hoenn.png", scale=2
            )
            with Image.open(path) as image:
                self.assertEqual(
                    image.size,
                    (REGION_COLS * REGION_TILE * 2, REGION_ROWS * REGION_TILE * 2),
                )


if __name__ == "__main__":
    unittest.main()
