import unittest

from game.rtc_events import BERRY_TREES_SIZE, RtcEventDashboard


class RtcEventDashboardTests(unittest.TestCase):
    def test_decodes_ready_and_growing_berry_trees(self) -> None:
        data = bytearray(BERRY_TREES_SIZE)
        data[0:6] = bytes((1, 5, 0, 0, 4, 0xF0))
        data[8:14] = bytes((2, 3, 30, 0, 0, 0x30))

        trees = RtcEventDashboard._berry_trees(bytes(data))

        self.assertEqual(len(trees), 2)
        self.assertEqual((trees[0].stage, trees[0].yield_count, trees[0].watered), (5, 4, 4))
        self.assertEqual((trees[1].stage, trees[1].minutes, trees[1].watered), (3, 30, 2))


if __name__ == "__main__":
    unittest.main()