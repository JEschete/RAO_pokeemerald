import unittest

from game.battle import (
    ITEM_EXP_SHARE,
    ITEM_LUCKY_EGG,
    ITEM_MACHO_BRACE,
    STATUS_SLEEP,
    TYPE_BUG,
    TYPE_WATER,
    ball_multiplier,
    catch_probability,
    ev_awards,
    experience_awards,
)
from game.state import PokemonState


def party_member(
    slot: int,
    *,
    item: int = 0,
    pokerus: int = 0,
    traded: bool = False,
    evs: tuple[int, int, int, int, int, int] = (0, 0, 0, 0, 0, 0),
) -> PokemonState:
    return PokemonState(
        slot=slot,
        species_id=1,
        species=f"SPECIES_TEST_{slot}",
        personality=slot,
        ot_id=slot,
        level=10,
        experience=100,
        held_item_id=item,
        moves=(0, 0, 0, 0),
        pp=(0, 0, 0, 0),
        pp_bonuses=0,
        friendship=70,
        evs=evs,
        contest=(0, 0, 0, 0, 0),
        sheen=0,
        pokerus=pokerus,
        ivs=(0, 0, 0, 0, 0, 0),
        is_egg=False,
        ability_slot=0,
        ribbons=0,
        status=0,
        hp=10,
        max_hp=10,
        stats=(10, 10, 10, 10, 10),
        is_traded=traded,
    )


class BallMultiplierTests(unittest.TestCase):
    def test_conditional_ball_multipliers(self) -> None:
        common = {"level": 20, "types": (0, 0), "caught": False, "underwater": False, "turns": 0}
        self.assertEqual(ball_multiplier(6, **(common | {"types": (TYPE_BUG, TYPE_WATER)})), 30)
        self.assertEqual(ball_multiplier(7, **(common | {"underwater": True})), 35)
        self.assertEqual(ball_multiplier(8, **common), 20)
        self.assertEqual(ball_multiplier(9, **(common | {"caught": True})), 30)
        self.assertEqual(ball_multiplier(10, **(common | {"turns": 50})), 40)


class CatchProbabilityTests(unittest.TestCase):
    def test_master_ball_is_certain(self) -> None:
        self.assertEqual(catch_probability(3, 100, 100, 0, 10, master_ball=True), 1.0)

    def test_low_hp_and_sleep_improve_probability(self) -> None:
        full_hp = catch_probability(45, 100, 100, 0, 10)
        weakened = catch_probability(45, 1, 100, STATUS_SLEEP, 10)
        self.assertGreater(weakened, full_hp)
        self.assertGreater(full_hp, 0)
        self.assertLess(weakened, 1)


class BattleRewardTests(unittest.TestCase):
    def test_experience_tracks_switches_share_lucky_egg_traded_and_trainer(self) -> None:
        party = (
            party_member(0, item=ITEM_LUCKY_EGG),
            party_member(1, traded=True),
            party_member(2, item=ITEM_EXP_SHARE),
        )

        awards = experience_awards(
            70,
            10,
            party,
            frozenset({0, 1}),
            trainer_battle=True,
        )

        self.assertEqual(awards, {0: 55, 1: 55, 2: 75})

    def test_ev_gain_applies_pokerus_macho_brace_share_and_caps(self) -> None:
        party = (
            party_member(0, pokerus=0x11),
            party_member(1, item=ITEM_MACHO_BRACE),
            party_member(2, item=ITEM_EXP_SHARE, pokerus=0x10),
            party_member(3, evs=(0, 0, 0, 252, 252, 6)),
        )

        awards = ev_awards(
            (0, 0, 0, 1, 0, 0),
            party,
            frozenset({0, 1, 3}),
        )

        self.assertEqual(awards[0], (0, 0, 0, 2, 0, 0))
        self.assertEqual(awards[1], (0, 0, 0, 2, 0, 0))
        self.assertEqual(awards[2], (0, 0, 0, 2, 0, 0))
        self.assertEqual(awards[3], (0, 0, 0, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()