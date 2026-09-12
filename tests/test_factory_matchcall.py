import unittest

from game.factory import (
    FactoryAdvisor,
    PLAYER_RENTALS,
    RENTALS_OFFSET,
    RENTAL_SIZE,
    RentalMon,
    decode_rentals,
)
from game.matchcall import MatchCallDashboard

TYPE_NORMAL = 0
TYPE_FIGHTING = 1
TYPE_WATER = 11
TYPE_GRASS = 12
TYPE_ELECTRIC = 13

CHART = (
    (TYPE_ELECTRIC, TYPE_WATER, 20),
    (TYPE_GRASS, TYPE_WATER, 20),
    (TYPE_WATER, TYPE_GRASS, 5),
    (TYPE_FIGHTING, TYPE_NORMAL, 20),
)

FRONTIER_MONS = [
    {},
    {"species": "SPECIES_AZUMARILL", "moves": [1], "item": 0, "nature": 0},
    {"species": "SPECIES_MARILL", "moves": [1], "item": 0, "nature": 0},
    {"species": "SPECIES_WAILMER", "moves": [1], "item": 0, "nature": 0},
    {"species": "SPECIES_ELECTRIKE", "moves": [2], "item": 0, "nature": 0},
]

SPECIES_INFO = {
    "SPECIES_AZUMARILL": {"types": [TYPE_WATER, TYPE_WATER]},
    "SPECIES_MARILL": {"types": [TYPE_WATER, TYPE_WATER]},
    "SPECIES_WAILMER": {"types": [TYPE_WATER, TYPE_WATER]},
    "SPECIES_ELECTRIKE": {"types": [TYPE_ELECTRIC, TYPE_ELECTRIC]},
}

MOVE_INFO = {
    1: {"name": "Water Gun", "power": 40, "type": TYPE_WATER},
    2: {"name": "Spark", "power": 65, "type": TYPE_ELECTRIC},
}


def rentals(*mon_ids: int) -> tuple[RentalMon, ...]:
    return tuple(
        RentalMon(mon_id=mon_id, personality=index, ivs=15, ability_slot=0)
        for index, mon_id in enumerate(mon_ids)
    )


class FactoryAdvisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.advisor = FactoryAdvisor(
            FRONTIER_MONS, SPECIES_INFO, MOVE_INFO, {0: "No item"}, CHART
        )

    def test_rentals_decode_from_frontier_block(self) -> None:
        data = bytearray(RENTALS_OFFSET + RENTAL_SIZE * 6)
        data[RENTALS_OFFSET : RENTALS_OFFSET + 2] = (2).to_bytes(2, "little")
        data[RENTALS_OFFSET + 4 : RENTALS_OFFSET + 8] = (99).to_bytes(4, "little")
        data[RENTALS_OFFSET + 8] = 31
        decoded = decode_rentals(bytes(data))
        self.assertEqual(len(decoded), 6)
        self.assertEqual(decoded[0].mon_id, 2)
        self.assertEqual(decoded[0].personality, 99)
        self.assertEqual(decoded[0].ivs, 31)

    def test_rental_rows_show_species_moves_and_ivs(self) -> None:
        rows = self.advisor.rental_rows(rentals(1, 2, 3, 0, 0, 0))
        self.assertEqual(len(rows), 6)
        self.assertIn("Azumarill", rows[0].text)
        self.assertIn("IVs 15", rows[0].text)
        self.assertEqual(rows[1].text, "Water Gun")

    def test_swap_advice_prefers_coverage_gains(self) -> None:
        # Three mono-Water rentals share a Grass/Electric weakness and only
        # hit Grass; taking Electrike adds coverage and breaks the shared
        # weakness.
        rows = self.advisor.swap_rows(rentals(1, 2, 3, 4, 0, 0))
        self.assertEqual(len(rows), 1)
        self.assertIn("→ Electrike", rows[0].text)
        self.assertEqual(rows[0].emphasis, "success")

    def test_swap_advice_keeps_a_better_team(self) -> None:
        advisor = FactoryAdvisor(
            FRONTIER_MONS, SPECIES_INFO, MOVE_INFO, {0: "No item"}, CHART
        )
        rows = advisor.swap_rows(rentals(4, 2, 3, 1, 0, 0))
        self.assertEqual(len(rows), 1)
        self.assertIn("keep", rows[0].text)

    def test_player_rentals_constant_matches_factory_party_size(self) -> None:
        self.assertEqual(PLAYER_RENTALS, 3)


class MatchCallTests(unittest.TestCase):
    def test_ready_rematches_span_all_maps(self) -> None:
        dashboard = MatchCallDashboard(
            {
                "ROUTE104": ((0, "Haley"), (2, "Cindy")),
                "ROUTE110": ((1, "Edwin"),),
            }
        )
        ready = bytearray(100)
        ready[0] = 1
        ready[1] = 1
        section = dashboard.section(bytes(ready))
        self.assertEqual(section.title, "Match Call · 2 ready")
        texts = [row.text for row in section.rows]
        self.assertIn("Haley · Route 104", texts)
        self.assertIn("Edwin · Route 110", texts)

    def test_no_section_when_nothing_is_ready(self) -> None:
        dashboard = MatchCallDashboard({"ROUTE104": ((0, "Haley"),)})
        self.assertIsNone(dashboard.section(bytes(100)))


if __name__ == "__main__":
    unittest.main()
