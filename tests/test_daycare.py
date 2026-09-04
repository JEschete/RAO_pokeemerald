import unittest

from game.daycare import DaycareDashboard
from game.state import BoxPokemonState


def box(species_id: int, species: str, personality: int, trainer_id: int) -> BoxPokemonState:
    return BoxPokemonState(
        species_id,
        species,
        personality,
        trainer_id,
        1000,
        0,
        70,
        False,
        0,
    )


class DaycareDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dashboard = DaycareDashboard(
            {25: "SPECIES_PIKACHU", 132: "SPECIES_DITTO"},
            {
                "SPECIES_PIKACHU": {
                    "egg_groups": [5, 6],
                    "gender_ratio": 127,
                    "growth_rate": "GROWTH_MEDIUM_FAST",
                    "abilities": [9, 0],
                },
                "SPECIES_DITTO": {
                    "egg_groups": [13, 13],
                    "gender_ratio": 255,
                    "growth_rate": "GROWTH_MEDIUM_FAST",
                    "abilities": [7, 0],
                },
            },
            {},
        )

    def test_same_species_opposite_gender_different_trainers_is_high(self) -> None:
        female = box(25, "SPECIES_PIKACHU", 1, 100)
        male = box(25, "SPECIES_PIKACHU", 200, 200)

        self.assertEqual(self.dashboard._compatibility(female, male), 70)

    def test_ditto_pair_is_incompatible(self) -> None:
        first = box(132, "SPECIES_DITTO", 1, 100)
        second = box(132, "SPECIES_DITTO", 2, 200)

        self.assertEqual(self.dashboard._compatibility(first, second), 0)


if __name__ == "__main__":
    unittest.main()