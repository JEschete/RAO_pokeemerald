import unittest

from game.frontier import (
    FACILITIES,
    FRONTIER_SIZE,
    BattleFrontierDashboard,
)


class FrontierMemory:
    def __init__(self, data: bytes = b"", facility: int = 0) -> None:
        self.data = data
        self.facility = facility

    def read_memory(self, address: int, size: int) -> bytes:
        if size == FRONTIER_SIZE and self.data:
            return self.data
        return self.facility.to_bytes(size, "little")


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

    def test_every_active_facility_is_named_from_its_runtime_id(self) -> None:
        dashboard = BattleFrontierDashboard(
            {"FLAG_SYS_GAME_CLEAR": 1},
            {"VAR_FRONTIER_FACILITY": 0x4000},
        )
        data = bytearray(FRONTIER_SIZE)
        data[0x65C] = 1

        for facility_id, name in enumerate(FACILITIES):
            with self.subTest(facility=name):
                section = dashboard.section(
                    FrontierMemory(bytes(data), facility_id),
                    0x02010000,
                    0x02020000,
                    bytes(0x200),
                )
                self.assertIn(f"Active · {name}", section.rows[1].text)


if __name__ == "__main__":
    unittest.main()