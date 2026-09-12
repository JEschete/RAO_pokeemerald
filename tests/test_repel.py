import unittest

from game.repel import repel_lead, repel_section, surviving_species
from tests.test_hunt import party_member

FIELD_DEFINITION = {"encounter_rates": [20, 20, 10, 10, 10, 10, 5, 5, 4, 4, 1, 1]}


def encounter_field(levels: list[tuple[int, int]]) -> dict:
    return {
        "mons": [
            {
                "species": f"SPECIES_MON_{index}",
                "min_level": low,
                "max_level": high,
            }
            for index, (low, high) in enumerate(levels)
        ]
    }


def display(value: str, prefix: str) -> str:
    return value.removeprefix(prefix)


class RepelTests(unittest.TestCase):
    def test_species_below_lead_level_are_blocked(self) -> None:
        field = encounter_field([(2, 3)] * 6 + [(4, 6)] * 6)
        surviving, blocked, total = surviving_species(
            FIELD_DEFINITION, field, 5
        )
        self.assertEqual(total, 100)
        self.assertEqual(blocked, 80)
        # Slots with max level >= 5 survive with their floor raised to 5.
        self.assertTrue(all(values["min"] == 5 for values in surviving.values()))

    def test_lead_skips_eggs(self) -> None:
        from dataclasses import replace

        egg = replace(party_member("SPECIES_TOGEPI", 1), is_egg=True)
        lead = repel_lead((egg, party_member("SPECIES_RALTS", 2)))
        self.assertIsNotNone(lead)
        self.assertEqual(lead.species, "SPECIES_RALTS")

    def test_section_summarizes_blocked_percentage(self) -> None:
        encounter = {
            "land_mons": encounter_field([(2, 3)] * 6 + [(4, 6)] * 6),
        }
        section = repel_section(
            {"land_mons": FIELD_DEFINITION},
            encounter,
            (party_member("SPECIES_RALTS", 2),),
            77,
            display,
        )
        self.assertIsNotNone(section)
        self.assertIn("Repel active · 77 steps", section.rows[0].text)
        self.assertTrue(
            any("blocks" in row.text for row in section.rows)
        )

    def test_section_absent_without_land_or_water_encounters(self) -> None:
        self.assertIsNone(
            repel_section(
                {"land_mons": FIELD_DEFINITION},
                {"rock_smash_mons": encounter_field([(5, 10)])},
                (party_member("SPECIES_RALTS", 2),),
                0,
                display,
            )
        )


if __name__ == "__main__":
    unittest.main()
