import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from game.hunt import HuntTracker
from game.state import BattlePokemonState, PokemonState
from game.tracker import BattleParticipationTracker


def wild(species: str, personality: int, hp: int) -> BattlePokemonState:
    return BattlePokemonState(
        species_id=1,
        species=species,
        level=5,
        hp=hp,
        max_hp=20,
        stats=(10, 10, 10, 10, 10),
        moves=(0, 0, 0, 0),
        pp=(0, 0, 0, 0),
        ivs=(0, 0, 0, 0, 0, 0),
        stat_stages=(6,) * 8,
        ability_id=0,
        ability_slot=0,
        types=(0, 0),
        held_item_id=0,
        friendship=0,
        personality=personality,
        status=0,
    )


def party_member(species: str, personality: int) -> PokemonState:
    return PokemonState(
        slot=0, species_id=1, species=species, personality=personality,
        ot_id=1, level=5, experience=100, held_item_id=0,
        moves=(0, 0, 0, 0), pp=(0, 0, 0, 0), pp_bonuses=0, friendship=70,
        evs=(0,) * 6, contest=(0,) * 5, sheen=0, pokerus=0, ivs=(0,) * 6,
        is_egg=False, ability_slot=0, ribbons=0, status=0, hp=19, max_hp=19,
        stats=(10, 10, 10, 10, 10), is_traded=False,
    )


class HuntTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.tracker = HuntTracker(Path(self._directory.name))
        self.tracker.select_playthrough(0xABCD1234)

    def tearDown(self) -> None:
        self._directory.cleanup()

    def test_repeated_snapshots_of_one_battle_count_one_encounter(self) -> None:
        self.tracker.battle_started(wild("SPECIES_RALTS", 42, 20), False)
        self.tracker.battle_started(wild("SPECIES_RALTS", 42, 12), False)
        self.assertEqual(self.tracker.session["SPECIES_RALTS"], 1)
        self.assertEqual(self.tracker.lifetime["SPECIES_RALTS"]["seen"], 1)

    def test_zero_hp_opponent_counts_as_knockout(self) -> None:
        self.tracker.battle_started(wild("SPECIES_RALTS", 42, 20), False)
        self.tracker.battle_started(wild("SPECIES_RALTS", 42, 0), False)
        outcome = self.tracker.battle_ended(False, ())
        self.assertEqual(outcome, "ko")
        self.assertEqual(self.tracker.lifetime["SPECIES_RALTS"]["ko"], 1)

    def test_new_dex_flag_counts_as_catch(self) -> None:
        self.tracker.battle_started(wild("SPECIES_RALTS", 42, 20), False)
        self.assertEqual(self.tracker.battle_ended(True, ()), "caught")

    def test_recatch_is_detected_through_party_personality(self) -> None:
        self.tracker.battle_started(wild("SPECIES_RALTS", 42, 20), True)
        outcome = self.tracker.battle_ended(
            True, (party_member("SPECIES_RALTS", 42),)
        )
        self.assertEqual(outcome, "caught")

    def test_everything_else_counts_as_fled(self) -> None:
        self.tracker.battle_started(wild("SPECIES_ZIGZAGOON", 7, 20), True)
        self.assertEqual(self.tracker.battle_ended(True, ()), "fled")

    def test_lifetime_stats_survive_reload_per_playthrough(self) -> None:
        self.tracker.battle_started(wild("SPECIES_RALTS", 42, 0), False)
        self.tracker.battle_ended(False, ())
        fresh = HuntTracker(Path(self._directory.name))
        fresh.select_playthrough(0xABCD1234)
        self.assertEqual(fresh.lifetime["SPECIES_RALTS"]["ko"], 1)
        self.assertEqual(fresh.session, {})
        other = HuntTracker(Path(self._directory.name))
        other.select_playthrough(0x11112222)
        self.assertEqual(other.lifetime, {})


class BattleParticipationTrackerTests(unittest.TestCase):
    def test_turn_zero_starts_a_new_participation_set(self) -> None:
        tracker = BattleParticipationTracker()
        first = party_member("SPECIES_FIRST", 1)
        second = replace(party_member("SPECIES_SECOND", 2), slot=1)

        tracker.update((first,), (wild("SPECIES_FIRST", 1, 10),), 0)
        participants = tracker.update(
            (second,), (wild("SPECIES_SECOND", 2, 10),), 0
        )

        self.assertEqual(participants, frozenset({1}))


if __name__ == "__main__":
    unittest.main()
