import unittest

from game.frontier import BattleFrontierDashboard, FRONTIER_SIZE


class FrontierMemory:
    def read_memory(self, address: int, size: int) -> bytes:
        return bytes(size)


class BattleFrontierDashboardTests(unittest.TestCase):
    def test_decodes_streaks_bp_and_pyramid_state(self) -> None:
        dashboard = BattleFrontierDashboard(
            {"FLAG_SYS_GAME_CLEAR": 1},
            {"VAR_FRONTIER_FACILITY": 0x40CF},
        )
        data = bytearray(FRONTIER_SIZE)
        data[0x694:0x696] = (14).to_bytes(2, "little")
        data[0x696:0x698] = (7).to_bytes(2, "little")
        data[0x7DE] = 0b00000111
        data[0x81C] = 4
        data[0x86C:0x86E] = (123).to_bytes(2, "little")

        streaks = dashboard._streaks(bytes(data))

        self.assertEqual((streaks[0].level_50, streaks[0].open_level), (14, 7))
        self.assertEqual(BattleFrontierDashboard._u16(data, 0x86C), 123)
        self.assertEqual(data[0x7DE].bit_count(), 3)


if __name__ == "__main__":
    unittest.main()