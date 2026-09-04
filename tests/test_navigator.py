import unittest

from game.navigator import ObjectiveNavigator


class ObjectiveNavigatorTests(unittest.TestCase):
    def test_removes_completed_story_goal_and_ranks_here_sidequest(self) -> None:
        flag_ids = {
            "FLAG_DEFEATED_RUSTBORO_GYM": 1,
            "FLAG_DELIVERED_STEVEN_LETTER": 2,
            "FLAG_RECEIVED_GOOD_ROD": 3,
        }
        flags = bytearray(4)
        flags[0] |= 1 << 1
        navigator = ObjectiveNavigator(
            flag_ids,
            {
                "Route118": ["MauvilleCity"],
                "MauvilleCity": ["Route118", "GraniteCave_StevensRoom"],
                "GraniteCave_StevensRoom": ["MauvilleCity"],
            },
        )

        section = navigator.section("Route118", bytes(flags))

        self.assertIsNotNone(section)
        assert section is not None
        text = "\n".join(row.text for row in section.rows)
        self.assertIn("Deliver Steven's letter", text)
        self.assertIn("Collect the Good Rod · here", text)
        self.assertNotIn("Earn the Stone Badge", text)


if __name__ == "__main__":
    unittest.main()