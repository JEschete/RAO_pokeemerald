import unittest

from game.damage import (
    damage_range,
    effectiveness_value,
    hits_to_ko,
    staged_stat,
    type_multipliers,
)

TYPE_ELECTRIC = 13
TYPE_WATER = 11
TYPE_FLYING = 2
TYPE_GROUND = 4
TYPE_NORMAL = 0

CHART = (
    (TYPE_ELECTRIC, TYPE_WATER, 20),
    (TYPE_ELECTRIC, TYPE_FLYING, 20),
    (TYPE_ELECTRIC, TYPE_GROUND, 0),
    (TYPE_WATER, TYPE_GROUND, 20),
)


class DamageTests(unittest.TestCase):
    def test_neutral_physical_damage_uses_gen_three_integer_math(self) -> None:
        low, high = damage_range(
            level=20,
            power=60,
            move_type=TYPE_NORMAL,
            attacker_types=(TYPE_WATER, TYPE_WATER),
            attack_stat=50,
            defense_stat=40,
            multipliers=(10,),
        )
        # ((2*20//5 + 2) * 60 * 50 // 40 // 50) + 2 = 17
        self.assertEqual(high, 17)
        self.assertEqual(low, 17 * 85 // 100)

    def test_stab_and_double_weakness_multiply_after_base(self) -> None:
        multipliers = type_multipliers(
            CHART, TYPE_ELECTRIC, (TYPE_WATER, TYPE_FLYING)
        )
        self.assertEqual(multipliers, (20, 20))
        self.assertEqual(effectiveness_value(multipliers), 4.0)
        _, neutral = damage_range(
            level=20, power=95, move_type=TYPE_ELECTRIC,
            attacker_types=(TYPE_NORMAL,), attack_stat=50, defense_stat=50,
            multipliers=(10,),
        )
        _, boosted = damage_range(
            level=20, power=95, move_type=TYPE_ELECTRIC,
            attacker_types=(TYPE_ELECTRIC,), attack_stat=50, defense_stat=50,
            multipliers=multipliers,
        )
        # STAB (x1.5) then two super-effective types (x2 each): at least 5x.
        self.assertGreater(boosted, neutral * 5)

    def test_immunity_returns_zero(self) -> None:
        multipliers = type_multipliers(CHART, TYPE_ELECTRIC, (TYPE_GROUND, TYPE_GROUND))
        self.assertEqual(
            damage_range(
                level=30, power=95, move_type=TYPE_ELECTRIC,
                attacker_types=(TYPE_ELECTRIC,), attack_stat=80,
                defense_stat=60, multipliers=multipliers,
            ),
            (0, 0),
        )

    def test_burn_halves_physical_but_not_special(self) -> None:
        physical_burned = damage_range(
            level=20, power=60, move_type=TYPE_NORMAL,
            attacker_types=(), attack_stat=50, defense_stat=40,
            multipliers=(10,), burned=True,
        )
        special_burned = damage_range(
            level=20, power=60, move_type=TYPE_WATER,
            attacker_types=(), attack_stat=50, defense_stat=40,
            multipliers=(10,), burned=True,
        )
        special_clean = damage_range(
            level=20, power=60, move_type=TYPE_WATER,
            attacker_types=(), attack_stat=50, defense_stat=40,
            multipliers=(10,),
        )
        self.assertLess(physical_burned[1], special_burned[1])
        self.assertEqual(special_burned, special_clean)

    def test_stat_stages_scale_with_the_gen_three_ratio_table(self) -> None:
        self.assertEqual(staged_stat(100, 6), 100)
        self.assertEqual(staged_stat(100, 8), 200)
        self.assertEqual(staged_stat(100, 4), 50)
        self.assertEqual(staged_stat(100, 0), 25)

    def test_hits_to_ko_uses_best_and_worst_rolls(self) -> None:
        self.assertEqual(hits_to_ko(100, 40, 55), (2, 3))
        self.assertEqual(hits_to_ko(30, 40, 55), (1, 1))
        self.assertEqual(hits_to_ko(100, 0, 0), (0, 0))


if __name__ == "__main__":
    unittest.main()
