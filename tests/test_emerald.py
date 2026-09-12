import unittest
import tempfile
from pathlib import Path

from game.adapter import (
    BALL_POCKET_OFFSET,
    BALL_POCKET_SIZE,
    BERRY_POCKET_OFFSET,
    BERRY_POCKET_SIZE,
    BATTLE_MON_SIZE,
    BATTLE_MONS_ADDRESS,
    BATTLE_RESULTS_TURN_ADDRESS,
    BATTLE_TYPE_FLAGS_ADDRESS,
    BATTLERS_COUNT_ADDRESS,
    DEX_FLAG_BYTES,
    FLAGS_OFFSET,
    FLAGS_SIZE,
    DEWFORD_TREND_SEED_OFFSET,
    DECORATION_INVENTORY_OFFSET,
    DECORATION_INVENTORY_SIZE,
    POKEDEX_OWNED_OFFSET,
    REMATCHES_OFFSET,
    REMATCHES_SIZE,
    ROAMER_LOCATION_ADDRESS,
    ROAMER_OFFSET,
    ROAMER_SIZE,
    PLAYER_POSITION_ADDRESS,
    PLAYER_PARTY_ADDRESS,
    PLAYER_PARTY_COUNT_ADDRESS,
    ENEMY_PARTY_ADDRESS,
    ENEMY_PARTY_COUNT_ADDRESS,
    POKEBLOCKS_OFFSET,
    POKEBLOCKS_SIZE,
    POKEMON_SIZE,
    SAVE_BLOCK_1_POINTER,
    SAVE_BLOCK_2_POINTER,
    SECURITY_KEY_OFFSET,
    SECRET_BASE_DECORATIONS_OFFSET,
    SECRET_BASE_DECORATIONS_SIZE,
    ITEM_POCKET_OFFSET,
    ITEM_POCKET_SIZE,
    MAIN_IN_BATTLE_ADDRESS,
    MAIN_IN_BATTLE_MASK,
    EmeraldAdapter,
)
from game.rtc_events import (
    BERRY_TREES_OFFSET,
    BERRY_TREES_SIZE,
    LAST_TIME_UPDATE_OFFSET,
    OUTBREAK_OFFSET,
    OUTBREAK_SIZE,
    TIME_SIZE,
    VARS_OFFSET,
    VARS_START,
)
from game.daycare import DAYCARE_OFFSET, DAYCARE_SIZE
from game.frontier import FRONTIER_OFFSET, FRONTIER_SIZE
from game.battle_view import BATTLE_TYPE_BATTLE_TOWER, BATTLE_TYPE_SAFARI
from retroarch_overlay.models import RetroArchStatus


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POKEEMERALD_ROOT = PROJECT_ROOT / "decomp_reference" / "pokeemerald"
requires_pokeemerald = unittest.skipUnless(
    (POKEEMERALD_ROOT / "src" / "data" / "wild_encounters.json").is_file(),
    "pokeemerald decomp checkout is not available",
)


class FakeMemory:
    def __init__(
        self,
        map_group: int,
        map_number: int,
        caught: tuple[int, ...] = (),
        badges: tuple[int, ...] = (),
        rematches: tuple[int, ...] = (),
        feebas_position: bytes | None = None,
        feebas_seed: int = 0,
        battle_mons: bytes | None = None,
        balls: dict[int, int] | None = None,
        roamer: tuple[int, int, int, int] | None = None,
        player_position: tuple[int, int] = (0, 0),
        in_battle: bool | None = None,
        battle_flags: int = 0,
        party: bytes = b"",
        player_trainer_id: int = 0x12345678,
        enemy_party: bytes = b"",
    ):
        self.save_block_1 = 0x02010000
        self.save_block_2 = 0x02020000
        self.map_group = map_group
        self.map_number = map_number
        self.player_position = player_position
        self.caught_flags = bytearray(DEX_FLAG_BYTES)
        for national_number in caught:
            bit_index = national_number - 1
            self.caught_flags[bit_index // 8] |= 1 << (bit_index % 8)
        self.event_flags = bytearray(FLAGS_SIZE)
        for badge in badges:
            flag_id = 0x867 + badge
            self.event_flags[flag_id // 8] |= 1 << (flag_id % 8)
        self.rematches = bytearray(REMATCHES_SIZE)
        for rematch in rematches:
            self.rematches[rematch] = 1
        self.feebas_position = feebas_position
        self.feebas_seed = feebas_seed
        self.battle_mons = battle_mons
        self.in_battle = battle_mons is not None if in_battle is None else in_battle
        self.battle_flags = battle_flags
        self.party = party
        self.player_trainer_id = player_trainer_id
        self.enemy_party = enemy_party
        self.pokeblocks = bytes(POKEBLOCKS_SIZE)
        self.berry_trees = bytes(BERRY_TREES_SIZE)
        self.outbreak = bytes(OUTBREAK_SIZE)
        self.variables: dict[int, int] = {}
        self.last_time_update = bytes(TIME_SIZE)
        self.daycare = bytes(DAYCARE_SIZE)
        self.frontier = bytes(FRONTIER_SIZE)
        self.security_key = 0x1234
        self.ball_pocket = bytearray(BALL_POCKET_SIZE)
        for slot, (item_id, quantity) in enumerate((balls or {}).items()):
            offset = slot * 4
            self.ball_pocket[offset : offset + 2] = item_id.to_bytes(2, "little")
            self.ball_pocket[offset + 2 : offset + 4] = (
                quantity ^ self.security_key
            ).to_bytes(2, "little")
        self.roamer = bytearray(ROAMER_SIZE)
        self.roamer_location = bytes(2)
        self.items = bytes(ITEM_POCKET_SIZE)
        self.berries = bytes(BERRY_POCKET_SIZE)
        self.decorations = bytes(DECORATION_INVENTORY_SIZE)
        self.placed_decorations = bytes(SECRET_BASE_DECORATIONS_SIZE)
        if roamer is not None:
            species_id, hp, roamer_group, roamer_number = roamer
            self.roamer[0x08:0x0A] = species_id.to_bytes(2, "little")
            self.roamer[0x0A:0x0C] = hp.to_bytes(2, "little")
            self.roamer[0x0C] = 40
            self.roamer[0x13] = 1
            self.roamer_location = bytes((roamer_group, roamer_number))

    def read_memory(self, address: int, size: int) -> bytes:
        if (address, size) == (SAVE_BLOCK_1_POINTER, 4):
            return self.save_block_1.to_bytes(4, "little")
        if (address, size) == (self.save_block_1 + 4, 2):
            return bytes((self.map_group, self.map_number))
        if (address, size) == (self.save_block_1, 4):
            return (
                self.player_position[0].to_bytes(2, "little", signed=True)
                + self.player_position[1].to_bytes(2, "little", signed=True)
            )
        if (address, size) == (SAVE_BLOCK_2_POINTER, 4):
            return self.save_block_2.to_bytes(4, "little")
        if (address, size) == (self.save_block_2 + 0x0A, 4):
            return self.player_trainer_id.to_bytes(4, "little")
        if (address, size) == (BATTLERS_COUNT_ADDRESS, 2):
            count = len(self.battle_mons) // BATTLE_MON_SIZE if self.battle_mons else 0
            return count.to_bytes(2, "little")
        if (address, size) == (MAIN_IN_BATTLE_ADDRESS, 1):
            return bytes((MAIN_IN_BATTLE_MASK if self.in_battle else 0,))
        if (address, size) == (PLAYER_PARTY_COUNT_ADDRESS, 1):
            return bytes((len(self.party) // POKEMON_SIZE,))
        if (address, size) == (ENEMY_PARTY_COUNT_ADDRESS, 1):
            return bytes((len(self.enemy_party) // POKEMON_SIZE,))
        if address == PLAYER_PARTY_ADDRESS:
            assert size == len(self.party)
            return self.party
        if address == ENEMY_PARTY_ADDRESS:
            assert size == len(self.enemy_party)
            return self.enemy_party
        if address == BATTLE_MONS_ADDRESS and self.battle_mons is not None:
            assert self.battle_mons is not None
            assert size == len(self.battle_mons)
            return self.battle_mons
        if (address, size) == (BATTLE_TYPE_FLAGS_ADDRESS, 4):
            return self.battle_flags.to_bytes(4, "little")
        if (address, size) == (BATTLE_RESULTS_TURN_ADDRESS, 1):
            return b"\x00"
        if (address, size) == (self.save_block_2 + SECURITY_KEY_OFFSET, 2):
            return self.security_key.to_bytes(2, "little")
        if (address, size) == (self.save_block_1 + BALL_POCKET_OFFSET, BALL_POCKET_SIZE):
            return bytes(self.ball_pocket)
        if (address, size) == (self.save_block_2 + POKEDEX_OWNED_OFFSET, DEX_FLAG_BYTES):
            return bytes(self.caught_flags)
        if (address, size) == (self.save_block_1 + FLAGS_OFFSET, FLAGS_SIZE):
            return bytes(self.event_flags)
        if (address, size) == (self.save_block_1 + REMATCHES_OFFSET, REMATCHES_SIZE):
            return bytes(self.rematches)
        if (address, size) == (self.save_block_1 + ROAMER_OFFSET, ROAMER_SIZE):
            return bytes(self.roamer)
        if (address, size) == (ROAMER_LOCATION_ADDRESS, 2):
            return self.roamer_location
        if (address, size) == (self.save_block_1 + ITEM_POCKET_OFFSET, ITEM_POCKET_SIZE):
            return self.items
        if (address, size) == (self.save_block_1 + BERRY_POCKET_OFFSET, BERRY_POCKET_SIZE):
            return self.berries
        if (address, size) == (self.save_block_1 + BERRY_TREES_OFFSET, BERRY_TREES_SIZE):
            return self.berry_trees
        if (address, size) == (self.save_block_1 + OUTBREAK_OFFSET, OUTBREAK_SIZE):
            return self.outbreak
        if (address, size) == (self.save_block_1 + DAYCARE_OFFSET, DAYCARE_SIZE):
            return self.daycare
        if (address, size) == (self.save_block_2 + FRONTIER_OFFSET, FRONTIER_SIZE):
            return self.frontier
        if (address, size) == (self.save_block_2 + LAST_TIME_UPDATE_OFFSET, TIME_SIZE):
            return self.last_time_update
        if size == 2 and self.save_block_1 + VARS_OFFSET <= address < self.save_block_1 + VARS_OFFSET + 0x200:
            variable_id = VARS_START + (address - self.save_block_1 - VARS_OFFSET) // 2
            return self.variables.get(variable_id, 0).to_bytes(2, "little")
        if (address, size) == (self.save_block_1 + POKEBLOCKS_OFFSET, POKEBLOCKS_SIZE):
            return self.pokeblocks
        if (address, size) == (self.save_block_1 + DECORATION_INVENTORY_OFFSET, DECORATION_INVENTORY_SIZE):
            return self.decorations
        if (address, size) == (self.save_block_1 + SECRET_BASE_DECORATIONS_OFFSET, SECRET_BASE_DECORATIONS_SIZE):
            return self.placed_decorations
        if (address, size) == (self.save_block_1 + DEWFORD_TREND_SEED_OFFSET, 2):
            return self.feebas_seed.to_bytes(2, "little")
        if (address, size) == (PLAYER_POSITION_ADDRESS, 9) and self.feebas_position is not None:
            return self.feebas_position
        raise AssertionError(f"Unexpected read: 0x{address:08X}, {size}")


@requires_pokeemerald
class EmeraldAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = EmeraldAdapter(POKEEMERALD_ROOT)

    def _wild_battle_mons(self) -> bytes:
        battle_mons = bytearray(BATTLE_MON_SIZE * 2)
        offset = BATTLE_MON_SIZE
        species_id = self.adapter._species_ids["SPECIES_ZIGZAGOON"]
        battle_mons[offset : offset + 2] = species_id.to_bytes(2, "little")
        battle_mons[offset + 0x21 : offset + 0x23] = bytes((0, 0))
        battle_mons[offset + 0x28 : offset + 0x2A] = (5).to_bytes(2, "little")
        battle_mons[offset + 0x2A] = 4
        battle_mons[offset + 0x2C : offset + 0x2E] = (12).to_bytes(2, "little")
        return bytes(battle_mons)

    def _double_battle_mons(self) -> bytes:
        battle_mons = bytearray(BATTLE_MON_SIZE * 4)
        for battler, species_name, hp in (
            (1, "SPECIES_ZIGZAGOON", 5),
            (3, "SPECIES_POOCHYENA", 0),
        ):
            offset = BATTLE_MON_SIZE * battler
            species_id = self.adapter._species_ids[species_name]
            battle_mons[offset : offset + 2] = species_id.to_bytes(2, "little")
            battle_mons[offset + 0x21 : offset + 0x23] = bytes((0, 0))
            battle_mons[offset + 0x28 : offset + 0x2A] = hp.to_bytes(2, "little")
            battle_mons[offset + 0x2A] = 4
            battle_mons[offset + 0x2C : offset + 0x2E] = (12).to_bytes(2, "little")
        return bytes(battle_mons)

    def _party_mon(
        self,
        species_name: str,
        level: int,
        experience: int,
        moves: tuple[int, ...] = (),
        held_item: int = 0,
        ot_id: int = 0x12345678,
    ) -> bytes:
        personality = 0
        secure = bytearray(48)
        species_id = self.adapter._species_ids[species_name]
        secure[0:2] = species_id.to_bytes(2, "little")
        secure[2:4] = held_item.to_bytes(2, "little")
        secure[4:8] = experience.to_bytes(4, "little")
        for index, move_id in enumerate(moves[:4]):
            offset = 12 + index * 2
            secure[offset : offset + 2] = move_id.to_bytes(2, "little")
        checksum = sum(
            int.from_bytes(secure[offset : offset + 2], "little")
            for offset in range(0, len(secure), 2)
        ) & 0xFFFF
        encrypted = b"".join(
            (int.from_bytes(secure[offset : offset + 4], "little") ^ ot_id).to_bytes(4, "little")
            for offset in range(0, len(secure), 4)
        )
        mon = bytearray(POKEMON_SIZE)
        mon[0:4] = personality.to_bytes(4, "little")
        mon[4:8] = ot_id.to_bytes(4, "little")
        mon[0x1C:0x1E] = checksum.to_bytes(2, "little")
        mon[0x20:0x50] = encrypted
        mon[0x54] = level
        mon[0x56:0x58] = (10).to_bytes(2, "little")
        mon[0x58:0x5A] = (10).to_bytes(2, "little")
        return bytes(mon)

    def test_every_encounter_map_has_an_id(self) -> None:
        self.assertEqual(set(self.adapter._encounters), set(self.adapter.map_ids))

    def test_numeric_defines_keep_full_species_trainer_and_flag_values(self) -> None:
        self.assertEqual(self.adapter._species_ids["SPECIES_POOCHYENA"], 286)
        self.assertEqual(self.adapter._trainer_ids["TRAINER_BRENDAN_ROUTE_110_MUDKIP"], 521)
        self.assertEqual(self.adapter._flag_ids["FLAG_RECEIVED_POWDER_JAR"], 0x151)

    def test_supports_installed_mgba_status_identifier(self) -> None:
        status = RetroArchStatus(
            "PLAYING",
            "game_boy_advance",
            "Pokemon - Emerald Version (USA, Europe),crc32=1f1c08fb",
        )
        self.assertTrue(self.adapter.supports(status))

    def test_uses_title_when_rom_is_outside_search_roots(self) -> None:
        status = RetroArchStatus(
            "PLAYING",
            "game_boy_advance",
            "Pokemon Emerald",
            "3c3c927f",
        )
        self.assertTrue(
            self.adapter.supports(status, "31446456df04356cb9f2145bada42ed2")
        )
        self.assertFalse(self.adapter.supports(status, "0" * 32))
        self.assertTrue(self.adapter.supports(status))

    def test_zero_save_pointer_waits_for_game(self) -> None:
        memory = FakeMemory(0, 0)
        memory.save_block_1 = 0
        snapshot = self.adapter.snapshot(memory)
        self.assertEqual(snapshot.location, "Waiting for game/save")
        self.assertEqual(snapshot.sections[0].rows[0].text, "Load or continue a save")
        self.assertTrue(snapshot.supports_caught_filter)

    def test_interior_without_encounters_has_a_location_name(self) -> None:
        snapshot = self.adapter.snapshot(FakeMemory(1, 2))
        self.assertEqual(snapshot.location, "Littleroot Town · Mays House · 1F")
        self.assertEqual(snapshot.sections[0].title, "Professor Oak Challenge")
        details = snapshot.sections[0].actions[0].rows
        self.assertEqual(
            details[0].text,
            "CURRENT AREA · LITTLEROOT TOWN · MAYS HOUSE · 1F",
        )
        self.assertIn(
            "No wild encounter data for this area.",
            {row.text for row in details},
        )
        self.assertEqual(snapshot.sections[-1].title, "Collections")

    def test_poc_details_change_with_current_route(self) -> None:
        route_101 = self.adapter.snapshot(
            FakeMemory(*self.adapter.map_ids["MAP_ROUTE101"])
        )
        route_104 = self.adapter.snapshot(
            FakeMemory(*self.adapter.map_ids["MAP_ROUTE104"])
        )

        route_101_rows = route_101.sections[0].actions[0].rows
        route_104_rows = route_104.sections[0].actions[0].rows
        self.assertEqual(route_101_rows[0].text, "CURRENT AREA · ROUTE 101")
        self.assertEqual(route_104_rows[0].text, "CURRENT AREA · ROUTE 104")
        self.assertNotEqual(route_101_rows, route_104_rows)

    def test_poc_progress_uses_set_badge_order(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]
        eligible = sorted(
            self.adapter._poc_planner.eligible_species(
                bytes(DEX_FLAG_BYTES), bytes(FLAGS_SIZE)
            ),
            key=self.adapter._national_dex_numbers.__getitem__,
        )
        caught = tuple(
            self.adapter._national_dex_numbers[species]
            for species in eligible[:39]
        )
        snapshot = self.adapter.snapshot(FakeMemory(map_group, map_number, caught, (0,)))
        self.assertEqual(
            snapshot.sections[0].rows[0].text,
            "Next: Wattson  39/66  need 27",
        )

    def test_poc_route_exp_uses_live_encrypted_party_experience(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]
        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                party=self._party_mon("SPECIES_TREECKO", 5, 150),
            )
        )
        details = snapshot.sections[0].actions[0].rows
        text = "\n".join(row.text for row in details)

        self.assertIn("CURRENT AREA EXP", text)
        self.assertIn("Land · 18.6 base solo XP", text)
        self.assertIn("Treecko 5→6 · 29 XP", text)
        self.assertNotIn("need verified party EXP memory offsets", text)

    def test_route_exp_estimate_applies_lucky_egg_and_traded_bonus(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]
        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                party=self._party_mon(
                    "SPECIES_TREECKO",
                    5,
                    150,
                    held_item=197,
                    ot_id=0x99999999,
                ),
            )
        )
        text = "\n".join(row.text for row in snapshot.sections[0].actions[0].rows)

        self.assertIn("Lucky Egg", text)
        self.assertIn("traded", text)
        self.assertIn("base solo XP", text)

    def test_party_and_contest_details_are_clickable(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]

        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                party=self._party_mon("SPECIES_TREECKO", 5, 150),
            )
        )

        party = next(section for section in snapshot.sections if section.title.startswith("Party ·"))
        contest = next(section for section in snapshot.sections if section.title == "Contests & ribbons")
        self.assertEqual(party.actions[0].label, "OPEN PARTY")
        self.assertIn("EVs", "\n".join(row.text for row in party.actions[0].rows))
        self.assertEqual(contest.actions[0].label, "OPEN CONTEST DETAILS")

    def test_poc_fishing_catch_rates_are_grouped_by_rod(self) -> None:
        snapshot = self.adapter.snapshot(
            FakeMemory(*self.adapter.map_ids["MAP_ROUTE104"])
        )
        rows = snapshot.sections[0].actions[0].rows
        fishing_rows = [
            row.text
            for row in rows
            if row.text.startswith(("Old Rod:", "Good Rod:", "Super Rod:"))
        ]

        self.assertTrue(fishing_rows)
        self.assertFalse(any("300%" in row or "130%" in row or "120%" in row for row in fishing_rows))

    def test_poc_route_exp_keeps_best_areas_seen_by_encounter_method(self) -> None:
        adapter = EmeraldAdapter(POKEEMERALD_ROOT)
        route_101 = adapter.snapshot(FakeMemory(*adapter.map_ids["MAP_ROUTE101"]))
        route_119 = adapter.snapshot(
            FakeMemory(
                *adapter.map_ids["MAP_ROUTE119"],
                feebas_position=bytes(9),
            )
        )
        route_101_revisit = adapter.snapshot(
            FakeMemory(*adapter.map_ids["MAP_ROUTE101"])
        )
        interior = adapter.snapshot(FakeMemory(1, 2))

        route_101_text = "\n".join(
            row.text for row in route_101.sections[0].actions[0].rows
        )
        route_119_text = "\n".join(
            row.text for row in route_119.sections[0].actions[0].rows
        )
        revisit_text = "\n".join(
            row.text for row in route_101_revisit.sections[0].actions[0].rows
        )
        interior_text = "\n".join(
            row.text for row in interior.sections[0].actions[0].rows
        )

        self.assertIn("Land · Route 101", route_101_text)
        self.assertIn("Land · Route 119", route_119_text)
        self.assertIn("Water · Route 119", route_119_text)
        self.assertIn("Fishing · Route 119", route_119_text)
        self.assertIn("Land · Route 119", revisit_text)
        self.assertIn("Land · Route 119", interior_text)
        self.assertIn("Water · Route 119", interior_text)
        self.assertIn("Fishing · Route 119", interior_text)

    def test_poc_route_exp_cache_persists_between_adapter_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_directory = Path(directory)
            first = EmeraldAdapter(POKEEMERALD_ROOT, state_directory=state_directory)
            first.snapshot(
                FakeMemory(
                    *first.map_ids["MAP_ROUTE119"],
                    feebas_position=bytes(9),
                )
            )

            second = EmeraldAdapter(POKEEMERALD_ROOT, state_directory=state_directory)
            interior = second.snapshot(FakeMemory(1, 2))
            text = "\n".join(row.text for row in interior.sections[0].actions[0].rows)

            self.assertIn("Land · Route 119", text)
            self.assertIn("Water · Route 119", text)
            self.assertIn("Fishing · Route 119", text)
            self.assertEqual(
                tuple(state_directory.glob("route-exp-*.json")),
                (state_directory / "route-exp-12345678.json",),
            )

    def test_training_cache_is_scoped_to_player_trainer_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_directory = Path(directory)
            first = EmeraldAdapter(POKEEMERALD_ROOT, state_directory=state_directory)
            first.snapshot(
                FakeMemory(
                    *first.map_ids["MAP_ROUTE119"],
                    feebas_position=bytes(9),
                    player_trainer_id=1,
                )
            )
            second = EmeraldAdapter(POKEEMERALD_ROOT, state_directory=state_directory)

            snapshot = second.snapshot(
                FakeMemory(
                    *second.map_ids["MAP_ROUTE101"],
                    player_trainer_id=2,
                )
            )
            text = "\n".join(row.text for row in snapshot.sections[0].actions[0].rows)

            self.assertNotIn("Route 119", text)
            self.assertEqual(
                {path.name for path in state_directory.glob("route-exp-*.json")},
                {"route-exp-00000001.json", "route-exp-00000002.json"},
            )

    def test_route_completion_is_derived_from_decomp_flags(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE104"]
        snapshot = self.adapter.snapshot(
            FakeMemory(map_group, map_number, player_position=(10, 10))
        )
        sections = {section.title: section for section in snapshot.sections}
        self.assertIn("Route trainers", sections)
        item_section = next(
            section for section in snapshot.sections if section.title.startswith("Route items")
        )
        self.assertEqual(item_section.title, "Route items · You (10,10)")
        self.assertEqual(item_section.rows[0].text, "0/9 complete")
        self.assertTrue(item_section.rows[0].text.endswith("complete"))
        self.assertTrue(any("(" in row.text for row in item_section.rows[1:]))
        self.assertFalse(any("Δ(" in row.text for row in item_section.rows[1:]))
        trainer_text = " ".join(row.text for row in sections["Route trainers"].rows)
        self.assertEqual(trainer_text.count("Rival Rustboro"), 1)

    def test_only_current_route_ready_rematches_are_shown(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE104"]
        route104_rematches = self.adapter._rematches_by_map["ROUTE104"]
        ready_index, ready_name = route104_rematches[0]
        snapshot = self.adapter.snapshot(
            FakeMemory(map_group, map_number, rematches=(ready_index,))
        )
        section = next(section for section in snapshot.sections if section.title == "Rematches ready")
        self.assertEqual(section.rows[0].text, ready_name)

    def test_feebas_alert_only_appears_when_facing_valid_tile(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE119"]
        seed = 12345
        spot_id = __import__(
            "game.feebas", fromlist=["feebas_spot_ids"]
        ).feebas_spot_ids(seed)[0]
        target_x, target_y = next(
            position
            for position, candidate in self.adapter._route119_fishing_spots.items()
            if candidate == spot_id
        )
        position = bytearray(9)
        position[0:2] = (target_x + 7).to_bytes(2, "little")
        position[2:4] = (target_y + 8).to_bytes(2, "little")
        position[8] = 2
        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                feebas_position=bytes(position),
                feebas_seed=seed,
            )
        )
        self.assertIn(
            "RA · One Tile Away from Beauty",
            {section.title for section in snapshot.sections},
        )

    def test_feebas_tile_list_is_available_everywhere_on_route_119(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE119"]

        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                feebas_position=bytes(9),
                feebas_seed=12345,
            )
        )

        section = next(section for section in snapshot.sections if section.title == "Feebas tiles")
        self.assertEqual(section.actions[0].label, "OPEN FEEBAS TILES")
        self.assertEqual(len(section.actions[0].rows), 6)

    def test_feebas_tile_list_deduplicates_repeated_spots(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE119"]

        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                feebas_position=bytes(9),
                feebas_seed=112,
            )
        )

        section = next(section for section in snapshot.sections if section.title == "Feebas tiles")
        self.assertEqual(len(section.actions[0].rows), 5)
        self.assertEqual(
            len({row.text for row in section.actions[0].rows}),
            len(section.actions[0].rows),
        )

    def test_zero_feebas_seed_adds_map_waypoints(self) -> None:
        from game.feebas import feebas_spot_ids
        from game.map_builder import load_map_catalog

        adapter = EmeraldAdapter(
            POKEEMERALD_ROOT, map_catalog=load_map_catalog(POKEEMERALD_ROOT)
        )
        map_group, map_number = adapter.map_ids["MAP_ROUTE119"]
        memory = FakeMemory(map_group, map_number, feebas_seed=0)

        overlays = adapter._map_marker_overlays(
            memory,
            memory.save_block_1,
            map_group,
            map_number,
            bytes(FLAGS_SIZE),
            bytes(DEX_FLAG_BYTES),
        )
        route119 = next(
            overlay for overlay in overlays if overlay.layer_key == "route119"
        )

        self.assertEqual(
            sum(waypoint.kind == "feebas" for waypoint in route119.waypoints),
            len(set(feebas_spot_ids(0))),
        )

    def test_wild_battle_replaces_overworld_with_catch_chances(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]
        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                battle_mons=self._wild_battle_mons(),
                balls={4: 5},
            )
        )
        self.assertEqual(snapshot.location, "Battle · Route 101")
        self.assertEqual(
            tuple(section.title for section in snapshot.sections),
            (
                "Battle",
                "Rewards if defeated",
                "Wild IVs · Zigzagoon",
                "Catch chances",
            ),
        )
        self.assertIn("Speed", snapshot.sections[1].rows[0].text)
        catch = snapshot.sections[3]
        self.assertIn("HP ", catch.rows[0].text)
        self.assertIn("Poké Ball x5", catch.rows[1].text)
        self.assertEqual(catch.rows[1].progress, catch.rows[1].progress)
        self.assertIsNotNone(catch.rows[1].progress)

    def test_frontier_battle_omits_rewards_the_game_does_not_grant(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]
        battle_mons = bytearray(self._wild_battle_mons())
        treecko = self.adapter._species_ids["SPECIES_TREECKO"]
        battle_mons[0:2] = treecko.to_bytes(2, "little")
        battle_mons[0x28:0x2A] = (10).to_bytes(2, "little")
        battle_mons[0x2A] = 5
        battle_mons[0x2C:0x2E] = (10).to_bytes(2, "little")

        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                battle_mons=bytes(battle_mons),
                party=self._party_mon("SPECIES_TREECKO", 5, 150),
                battle_flags=(1 << 3) | BATTLE_TYPE_BATTLE_TOWER,
            )
        )

        self.assertNotIn(
            "Rewards if defeated", {section.title for section in snapshot.sections}
        )

    def test_safari_battle_omits_normal_bag_ball_advice(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]

        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                battle_mons=self._wild_battle_mons(),
                balls={4: 5},
                battle_flags=BATTLE_TYPE_SAFARI,
            )
        )

        self.assertNotIn(
            "Catch chances", {section.title for section in snapshot.sections}
        )

    def test_double_battle_shows_both_opponents(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]
        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                battle_mons=self._double_battle_mons(),
                battle_flags=(1 << 0) | (1 << 3),
            )
        )

        self.assertEqual(len(snapshot.sections[0].rows), 2)
        self.assertIn("Zigzagoon", snapshot.sections[0].rows[0].text)
        self.assertIn("Poochyena", snapshot.sections[0].rows[1].text)
        self.assertIn("FNT", snapshot.sections[0].rows[1].text)
        self.assertEqual(
            tuple(section.title for section in snapshot.sections),
            ("Battle", "Rewards if defeated"),
        )

    def test_battle_uses_runtime_enemy_team_and_projects_party_rewards(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]
        battle_mons = bytearray(self._wild_battle_mons())
        player_species = self.adapter._species_ids["SPECIES_TREECKO"]
        battle_mons[0:2] = player_species.to_bytes(2, "little")
        battle_mons[0x28:0x2A] = (10).to_bytes(2, "little")
        battle_mons[0x2A] = 5
        battle_mons[0x2C:0x2E] = (10).to_bytes(2, "little")

        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                battle_mons=bytes(battle_mons),
                party=self._party_mon("SPECIES_TREECKO", 5, 150),
                enemy_party=self._party_mon("SPECIES_ZIGZAGOON", 4, 100),
                battle_flags=1 << 3,
            )
        )

        team = next(section for section in snapshot.sections if section.title == "Opponent team · 1")
        rewards = next(section for section in snapshot.sections if section.title == "Rewards if defeated")
        self.assertEqual(team.actions[0].label, "OPEN OPPONENT TEAM")
        self.assertIn("Zigzagoon", team.rows[0].text)
        self.assertIn("Treecko", "\n".join(row.text for row in rewards.rows))
        self.assertIn("XP", "\n".join(row.text for row in rewards.rows))

    def test_battle_advice_uses_current_moves_and_runtime_enemy_moves(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE103"]
        battle_mons = bytearray(BATTLE_MON_SIZE * 2)
        pikachu = self.adapter._species_ids["SPECIES_PIKACHU"]
        wingull = self.adapter._species_ids["SPECIES_WINGULL"]
        for offset, species, level in ((0, pikachu, 20), (BATTLE_MON_SIZE, wingull, 12)):
            battle_mons[offset : offset + 2] = species.to_bytes(2, "little")
            battle_mons[offset + 0x06 : offset + 0x08] = (30).to_bytes(2, "little")
            battle_mons[offset + 0x28 : offset + 0x2A] = (30).to_bytes(2, "little")
            battle_mons[offset + 0x2A] = level
            battle_mons[offset + 0x2C : offset + 0x2E] = (30).to_bytes(2, "little")
        battle_mons[0x21:0x23] = bytes((13, 13))
        battle_mons[BATTLE_MON_SIZE + 0x21 : BATTLE_MON_SIZE + 0x23] = bytes((11, 2))
        thunderbolt = 85
        water_gun = 55

        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                battle_mons=bytes(battle_mons),
                battle_flags=1 << 3,
                party=self._party_mon("SPECIES_PIKACHU", 20, 8000, (thunderbolt,)),
                enemy_party=self._party_mon("SPECIES_WINGULL", 12, 1000, (water_gun,)),
            )
        )

        advice = next(section for section in snapshot.sections if section.title == "Battle advice")
        self.assertIn("Thunderbolt", advice.rows[0].text)
        self.assertIn("%", advice.rows[0].text)
        self.assertEqual(advice.rows[0].chips[0].text, "4X")

    def test_stale_battle_globals_do_not_replace_overworld(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]
        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                battle_mons=self._wild_battle_mons(),
                in_battle=False,
            )
        )
        self.assertFalse(snapshot.location.startswith("Battle"))

    def test_roamer_alert_only_appears_on_same_route(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE110"]
        latios = self.adapter._species_ids["SPECIES_LATIOS"]
        snapshot = self.adapter.snapshot(
            FakeMemory(
                map_group,
                map_number,
                roamer=(latios, 91, map_group, map_number),
            )
        )
        section = next(
            section
            for section in snapshot.sections
            if section.title == "RA · Flying Through the Eons"
        )
        self.assertIn("Latios IS ON THIS ROUTE", section.rows[0].text)

    def test_relevant_route_achievement_is_explicitly_tracked(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE103"]
        snapshot = self.adapter.snapshot(FakeMemory(map_group, map_number))
        section = next(section for section in snapshot.sections if section.title == "RA nearby")
        self.assertEqual(section.rows[0].text, "Let's Have a Quick Battle!")

    def test_gym_missable_alert_is_first_and_strong(self) -> None:
        map_group, map_number = next(
            map_id
            for map_id, map_name in self.adapter._map_constants_by_id.items()
            if map_name == "RustboroCity_Gym"
        )
        snapshot = self.adapter.snapshot(FakeMemory(map_group, map_number))

        self.assertTrue(snapshot.sections[0].alert)
        self.assertEqual(
            snapshot.sections[0].title,
            "MISSABLE · Battle Addict - Rustboro",
        )

    def test_route_101_snapshot_contains_land_encounters(self) -> None:
        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]
        poochyena = self.adapter._national_dex_numbers["SPECIES_POOCHYENA"]
        snapshot = self.adapter.snapshot(FakeMemory(map_group, map_number, (poochyena,)))
        self.assertEqual(snapshot.location, "Route 101")
        land = next(section for section in snapshot.sections if section.title == "Land · rate 20")
        rows = "\n".join(row.text for row in land.rows)
        self.assertIn("Poochyena", rows)
        self.assertIn("Wurmple", rows)
        caught = {row.text.split()[0]: row.caught for row in land.rows}
        self.assertTrue(caught["Poochyena"])
        self.assertFalse(caught["Wurmple"])

    def test_optional_feature_failure_does_not_hide_encounters(self) -> None:
        class BrokenWorldEvents(FakeMemory):
            def read_memory(self, address: int, size: int) -> bytes:
                if (address, size) == (
                    self.save_block_1 + BERRY_TREES_OFFSET,
                    BERRY_TREES_SIZE,
                ):
                    raise ValueError("bad berry data")
                return super().read_memory(address, size)

        map_group, map_number = self.adapter.map_ids["MAP_ROUTE101"]

        snapshot = self.adapter.snapshot(BrokenWorldEvents(map_group, map_number))

        self.assertIn("Land · rate 20", {section.title for section in snapshot.sections})
        unavailable = next(
            section
            for section in snapshot.sections
            if section.title == "World events unavailable"
        )
        self.assertIn("bad berry data", unavailable.rows[0].text)


if __name__ == "__main__":
    unittest.main()