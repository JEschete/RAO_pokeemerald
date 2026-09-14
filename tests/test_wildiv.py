import unittest
from dataclasses import replace

from game.wildiv import WildScout, build_family_map
from game.state import BoxPokemonState, StoredPokemonState
from tests.test_hunt import party_member, wild

EVOLUTIONS = {
    "SPECIES_RALTS": [
        {"method": "EVO_LEVEL", "parameter": "20", "target": "SPECIES_KIRLIA"}
    ],
    "SPECIES_KIRLIA": [
        {"method": "EVO_LEVEL", "parameter": "30", "target": "SPECIES_GARDEVOIR"}
    ],
}


class WildScoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scout = WildScout(build_family_map(EVOLUTIONS))

    def test_family_map_links_the_whole_line(self) -> None:
        self.assertEqual(
            self.scout.family_of("SPECIES_RALTS"),
            self.scout.family_of("SPECIES_GARDEVOIR"),
        )
        self.assertNotEqual(
            self.scout.family_of("SPECIES_RALTS"),
            self.scout.family_of("SPECIES_ZIGZAGOON"),
        )

    def test_wild_with_higher_total_is_marked_as_upgrade(self) -> None:
        opponent = replace(wild("SPECIES_RALTS", 42, 20), ivs=(31,) * 6)
        member = replace(
            party_member("SPECIES_GARDEVOIR", 7), ivs=(10,) * 6
        )
        section = self.scout.section(opponent, (member,))
        verdict = section.rows[-1]
        self.assertEqual(verdict.emphasis, "success")
        self.assertEqual(verdict.chips[0].text, f"UPGRADE +{31 * 6 - 60}")

    def test_wild_with_lower_total_defers_to_the_party(self) -> None:
        opponent = replace(wild("SPECIES_RALTS", 42, 20), ivs=(5,) * 6)
        member = replace(
            party_member("SPECIES_KIRLIA", 7), ivs=(20,) * 6
        )
        verdict = self.scout.section(opponent, (member,)).rows[-1]
        self.assertEqual(verdict.emphasis, "muted")
        self.assertIn("Kirlia is better", verdict.text)

    def test_wild_with_equal_total_is_reported_as_a_tie(self) -> None:
        opponent = replace(wild("SPECIES_RALTS", 42, 20), ivs=(10,) * 6)
        member = replace(
            party_member("SPECIES_KIRLIA", 7), ivs=(10,) * 6
        )

        verdict = self.scout.section(opponent, (member,)).rows[-1]

        self.assertIn("Same IV total", verdict.text)
        self.assertEqual(verdict.chips[0].text, "TIED")

    def test_unowned_family_is_called_out(self) -> None:
        opponent = replace(wild("SPECIES_RALTS", 42, 20), ivs=(5,) * 6)
        verdict = self.scout.section(
            opponent, (party_member("SPECIES_ZIGZAGOON", 7),)
        ).rows[-1]
        self.assertIn("No party or boxed", verdict.text)

    def test_boxed_family_member_participates_in_comparison(self) -> None:
        opponent = replace(wild("SPECIES_RALTS", 42, 20), ivs=(20,) * 6)
        boxed = StoredPokemonState(
            4,
            9,
            BoxPokemonState(
                282,
                "SPECIES_GARDEVOIR",
                1,
                2,
                1000,
                0,
                70,
                False,
                0,
                (31,) * 6,
            ),
        )

        verdict = self.scout.section(opponent, (), (boxed,)).rows[-1]

        self.assertIn("Gardevoir is better", verdict.text)
        self.assertIn("Box 4, slot 9", verdict.text)


if __name__ == "__main__":
    unittest.main()
