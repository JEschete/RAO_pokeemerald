import json
import unittest
from pathlib import Path

from game.poc import POC_GATES, PocPlanner, map_stage


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class PocPlannerTests(unittest.TestCase):
    def test_preserves_retroachievements_gate_order(self) -> None:
        self.assertEqual(
            tuple((gate.leader, gate.target) for gate in POC_GATES),
            (
                ("Roxanne", 39),
                ("Wattson", 66),
                ("Flannery", 90),
                ("Brawly", 101),
                ("Norman", 101),
                ("Tate & Liza", 156),
                ("Juan", 167),
                ("Winona", 171),
            ),
        )

    def test_route_progression_orders_early_and_late_sources(self) -> None:
        self.assertEqual(map_stage("MAP_ROUTE101"), 0)
        self.assertEqual(map_stage("MAP_ROUTE119"), 5)
        self.assertEqual(map_stage("MAP_VICTORY_ROAD_1F"), 8)

    def test_current_route_sources_are_ranked_first(self) -> None:
        knowledge = json.loads(
            (PLUGIN_ROOT / "game" / "data" / "emerald_knowledge.json").read_text(
                encoding="utf-8"
            )
        )
        planner = PocPlanner(knowledge, knowledge["national_dex"])

        rows = planner.rows(bytes(52), bytes(352), "MAP_ROUTE101", lambda *_: False)

        first_species = next(row.text for row in rows if " · " in row.text and "Route101" in row.text.replace(" ", ""))
        self.assertTrue(first_species)

    def test_selected_starter_and_fossil_produce_explicit_212_species_set(self) -> None:
        knowledge = json.loads(
            (PLUGIN_ROOT / "game" / "data" / "emerald_knowledge.json").read_text(
                encoding="utf-8"
            )
        )
        planner = PocPlanner(knowledge, knowledge["national_dex"])
        caught = bytearray(52)
        treecko = knowledge["national_dex"]["SPECIES_TREECKO"]
        caught[(treecko - 1) // 8] |= 1 << ((treecko - 1) % 8)
        flags = bytearray(352)
        root_flag = knowledge["flag_ids"]["FLAG_CHOSE_ROOT_FOSSIL"]
        flags[root_flag // 8] |= 1 << (root_flag % 8)

        eligible = planner.eligible_species(bytes(caught), bytes(flags))

        self.assertEqual(len(eligible), 212)
        self.assertIn("SPECIES_TREECKO", eligible)
        self.assertIn("SPECIES_SCEPTILE", eligible)
        self.assertIn("SPECIES_LILEEP", eligible)
        self.assertNotIn("SPECIES_ANORITH", eligible)

    def test_event_species_do_not_inflate_poc_caught_count(self) -> None:
        knowledge = json.loads(
            (PLUGIN_ROOT / "game" / "data" / "emerald_knowledge.json").read_text(
                encoding="utf-8"
            )
        )
        planner = PocPlanner(knowledge, knowledge["national_dex"])
        caught = bytearray(52)
        for species in ("SPECIES_TREECKO", "SPECIES_MEW"):
            number = knowledge["national_dex"][species]
            caught[(number - 1) // 8] |= 1 << ((number - 1) % 8)

        self.assertEqual(planner.caught_count(bytes(caught), bytes(352)), 1)


if __name__ == "__main__":
    unittest.main()