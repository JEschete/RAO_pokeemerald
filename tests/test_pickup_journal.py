import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from game.journal import EventDetector, SessionJournal, BADGE_FLAG_START
from game.pickup import ABILITY_PICKUP, PickupWatcher
from tests.test_hunt import party_member

SPECIES_INFO = {
    "SPECIES_ZIGZAGOON": {"abilities": [ABILITY_PICKUP, 0]},
    "SPECIES_RALTS": {"abilities": [26, 0]},
}
ITEM_NAMES = {13: "Potion"}


class PickupWatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.watcher = PickupWatcher(SPECIES_INFO, ITEM_NAMES)

    def test_new_item_on_a_pickup_member_is_reported_once(self) -> None:
        empty = (party_member("SPECIES_ZIGZAGOON", 5),)
        holding = (
            replace(party_member("SPECIES_ZIGZAGOON", 5), held_item_id=13),
        )
        self.assertEqual(self.watcher.observe("tid", empty), [])
        self.assertEqual(
            self.watcher.observe("tid", holding),
            ["Zigzagoon picked up Potion"],
        )
        self.assertEqual(self.watcher.observe("tid", holding), [])

    def test_non_pickup_members_are_ignored(self) -> None:
        first = (party_member("SPECIES_RALTS", 5),)
        second = (replace(party_member("SPECIES_RALTS", 5), held_item_id=13),)
        self.watcher.observe("tid", first)
        self.assertEqual(self.watcher.observe("tid", second), [])
        self.assertIsNone(self.watcher.section(second))

    def test_section_counts_held_items(self) -> None:
        holding = (
            replace(party_member("SPECIES_ZIGZAGOON", 5), held_item_id=13),
        )
        section = self.watcher.section(holding)
        self.assertEqual(section.title, "Pickup · 1 to collect")
        self.assertIn("holding Potion", section.rows[0].text)


class EventDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = EventDetector(
            {280: "SPECIES_RALTS"},
            {"FLAG_SYS_TOWER_SILVER": 0x8D0},
        )
        self.caught = bytearray(52)
        self.flags = bytearray(0x160)
        self.party = (party_member("SPECIES_RALTS", 9),)

    def observe(self):
        return self.detector.observe(
            "tid", bytes(self.caught), bytes(self.flags), self.party
        )

    def test_first_observation_is_a_baseline(self) -> None:
        self.assertEqual(self.observe(), [])

    def test_new_dex_flag_becomes_a_caught_event(self) -> None:
        self.observe()
        bit = 280 - 1
        self.caught[bit // 8] |= 1 << (bit % 8)
        self.assertEqual(self.observe(), [("caught", "Caught Ralts")])

    def test_badge_and_symbol_flags_are_reported(self) -> None:
        self.observe()
        self.flags[BADGE_FLAG_START // 8] |= 1 << (BADGE_FLAG_START % 8)
        self.flags[0x8D0 // 8] |= 1 << (0x8D0 % 8)
        events = self.observe()
        self.assertIn(("badge", "Earned the Stone Badge"), events)
        self.assertIn(("symbol", "Earned the Tower Silver symbol"), events)

    def test_level_up_and_evolution_are_reported(self) -> None:
        self.observe()
        self.party = (replace(party_member("SPECIES_RALTS", 9), level=6),)
        self.assertEqual(self.observe(), [("level", "Ralts grew to Lv 6")])
        self.party = (replace(party_member("SPECIES_KIRLIA", 9), level=6),)
        self.assertEqual(
            self.observe(), [("evolution", "Ralts evolved into Kirlia")]
        )


class SessionJournalTests(unittest.TestCase):
    def test_events_persist_and_render_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = SessionJournal(Path(directory))
            journal.select_playthrough(0x1234)
            journal.record("caught", "Caught Ralts")
            journal.record("badge", "Earned the Stone Badge")
            section = journal.section()
            self.assertEqual(section.title, "Journal")
            self.assertIn("Stone Badge", section.rows[0].text)
            markdown = journal.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Caught Ralts", markdown)

            fresh = SessionJournal(Path(directory))
            fresh.select_playthrough(0x1234)
            self.assertEqual(len(fresh.events), 2)


if __name__ == "__main__":
    unittest.main()
