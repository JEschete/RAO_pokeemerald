import unittest

from game.legendary import LegendaryDashboard


class LegendaryDashboardTests(unittest.TestCase):
    def test_contains_only_vanilla_solo_targets_and_tracks_state(self) -> None:
        flag_ids = {
            "FLAG_SOOTOPOLIS_ARCHIE_MAXIE_LEAVE": 1,
            "FLAG_DEFEATED_RAYQUAZA": 2,
        }
        flags = bytes((1 << 1,))
        national = {
            "SPECIES_RAYQUAZA": 384,
            "SPECIES_GROUDON": 383,
            "SPECIES_KYOGRE": 382,
            "SPECIES_REGIROCK": 377,
            "SPECIES_REGICE": 378,
            "SPECIES_REGISTEEL": 379,
            "SPECIES_LATIAS": 380,
            "SPECIES_LATIOS": 381,
        }
        dashboard = LegendaryDashboard(flag_ids, national)

        section = dashboard.section(flags, bytes(52), bytes(28))
        text = "\n".join(row.text for row in section.actions[0].rows)

        self.assertIn("Rayquaza · Sky Pillar · Available", text)
        self.assertNotIn("Mew", text)
        self.assertNotIn("Deoxys", text)
        self.assertNotIn("Ho Oh", text)
        self.assertNotIn("Lugia", text)


if __name__ == "__main__":
    unittest.main()