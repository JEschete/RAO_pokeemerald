from dataclasses import dataclass

from retroarch_overlay.core.contracts import MemoryReader
from retroarch_overlay.models import PanelAction, PanelRow, PanelSection

from .factory import FactoryAdvisor, decode_rentals


FRONTIER_OFFSET = 0x64C
FRONTIER_SIZE = 0x874
VARS_OFFSET = 0x139C
VARS_START = 0x4000

FACILITIES = (
    "Tower",
    "Dome",
    "Palace",
    "Arena",
    "Factory",
    "Pike",
    "Pyramid",
)

SYMBOL_FLAGS = tuple(
    (facility, color, f"FLAG_SYS_{facility.upper()}_{color.upper()}")
    for facility in FACILITIES
    for color in ("Silver", "Gold")
)


@dataclass(frozen=True, slots=True)
class FacilityStreak:
    facility: str
    level_50: int
    open_level: int
    extra: str = ""


class BattleFrontierDashboard:
    def __init__(
        self,
        flag_ids: dict[str, int],
        variable_ids: dict[str, int],
        factory_advisor: FactoryAdvisor | None = None,
    ) -> None:
        self._flag_ids = flag_ids
        self._variable_ids = variable_ids
        self._factory_advisor = factory_advisor

    def section(
        self,
        memory: MemoryReader,
        save_block_1: int,
        save_block_2: int,
        flags: bytes,
    ) -> PanelSection:
        data = memory.read_memory(save_block_2 + FRONTIER_OFFSET, FRONTIER_SIZE)
        if len(data) != FRONTIER_SIZE:
            raise ValueError(
                f"Expected {FRONTIER_SIZE} Battle Frontier bytes, received {len(data)}"
            )
        symbols = [
            f"{facility} {color}"
            for facility, color, flag in SYMBOL_FLAGS
            if self._flag(flags, flag)
        ]
        bp = self._u16(data, 0x86C)
        battles = int.from_bytes(data[0x870:0x874], "little")
        challenge_status = data[0x65C]
        level_mode = data[0x65D] & 0x3
        challenge_number = self._u16(data, 0x666)
        facility_id = self._variable(memory, save_block_1, "VAR_FRONTIER_FACILITY")
        facility_name = FACILITIES[facility_id] if facility_id < len(FACILITIES) else f"Facility {facility_id}"
        streaks = self._streaks(data)
        rows = [
            PanelRow(
                f"BP {bp} · Symbols {len(symbols)}/14 · Battles {battles}",
                progress=len(symbols) / 14,
                progress_color="accent",
            )
        ]
        if challenge_status:
            rows.append(
                PanelRow(
                    f"Active · {facility_name} · {'Lv 50' if level_mode == 0 else 'Open Lv'} · "
                    f"battle/room {challenge_number + 1}"
                )
            )
        elif not self._flag(flags, "FLAG_SYS_GAME_CLEAR"):
            rows.append(PanelRow("Locked until the Hall of Fame"))
        factory_rows: list[PanelRow] = []
        if self._factory_advisor is not None:
            rentals = decode_rentals(data)
            rental_rows = self._factory_advisor.rental_rows(rentals)
            if rental_rows:
                factory_rows.append(PanelRow("FACTORY RENTALS"))
                factory_rows.extend(rental_rows)
                factory_rows.extend(self._factory_advisor.swap_rows(rentals))
            if (
                challenge_status
                and facility_name == "Factory"
                and factory_rows
            ):
                advice = [
                    row
                    for row in factory_rows
                    if row.emphasis in {"success", "muted"} and "Swap" in row.text
                ]
                rows.extend(advice[:1])

        details = [PanelRow("BATTLE FRONTIER")]
        details.extend(
            PanelRow(
                f"{streak.facility} · Lv 50 {streak.level_50} · "
                f"Open Lv {streak.open_level}"
                f"{f' · {streak.extra}' if streak.extra else ''}"
            )
            for streak in streaks
        )
        details.append(PanelRow("SYMBOLS"))
        details.extend(
            PanelRow(f"{facility} · {color}", flag in {item[2] for item in SYMBOL_FLAGS if self._flag(flags, item[2])})
            for facility, color, flag in SYMBOL_FLAGS
        )
        details.extend(
            (
                PanelRow("CURRENT CHALLENGE"),
                PanelRow(f"Status {challenge_status} · {facility_name} · mode {level_mode}"),
                PanelRow(
                    "Selected party slots · "
                    + ", ".join(
                        str(self._u16(data, 0x65E + index * 2))
                        for index in range(3)
                    )
                ),
                PanelRow(
                    f"Pyramid · floor {challenge_number + 1} · "
                    f"trainers defeated {data[0x7DE].bit_count()}/8 · "
                    f"light radius {data[0x81C]}"
                ),
                PanelRow(
                    f"Pyramid bag · {self._pyramid_item_count(data, level_mode)} occupied slot(s)"
                ),
            )
        )
        details.extend(factory_rows)
        return PanelSection(
            "Battle Frontier",
            tuple(rows),
            actions=(PanelAction("OPEN FRONTIER DASHBOARD", "Battle Frontier Dashboard", tuple(details)),),
            priority=20,
            role="goals",
            compact_rows=(rows[0],),
        )

    def _streaks(self, data: bytes) -> tuple[FacilityStreak, ...]:
        tower = FacilityStreak("Tower Singles", self._u16(data, 0x694), self._u16(data, 0x696))
        dome = FacilityStreak("Dome Singles", self._u16(data, 0x6C0), self._u16(data, 0x6C2))
        palace = FacilityStreak("Palace Singles", self._u16(data, 0x77C), self._u16(data, 0x77E))
        arena = FacilityStreak("Arena", self._u16(data, 0x78E), self._u16(data, 0x790))
        factory = FacilityStreak(
            "Factory Singles",
            self._u16(data, 0x796),
            self._u16(data, 0x798),
            f"rentals {self._u16(data, 0x7AA)}/{self._u16(data, 0x7AC)}",
        )
        pike = FacilityStreak("Pike", self._u16(data, 0x7B8), self._u16(data, 0x7BA))
        pyramid = FacilityStreak("Pyramid", self._u16(data, 0x7CE), self._u16(data, 0x7D0))
        return tower, dome, palace, arena, factory, pike, pyramid

    @staticmethod
    def _u16(data: bytes, offset: int) -> int:
        return int.from_bytes(data[offset : offset + 2], "little")

    @staticmethod
    def _pyramid_item_count(data: bytes, level_mode: int) -> int:
        mode = 0 if level_mode == 0 else 1
        start = 0x7E0 + mode * 20
        return sum(
            bool(int.from_bytes(data[offset : offset + 2], "little"))
            for offset in range(start, start + 20, 2)
        )

    def _variable(self, memory: MemoryReader, save_block_1: int, name: str) -> int:
        variable_id = self._variable_ids[name]
        return int.from_bytes(
            memory.read_memory(
                save_block_1 + VARS_OFFSET + (variable_id - VARS_START) * 2,
                2,
            ),
            "little",
        )

    def _flag(self, flags: bytes, name: str) -> bool:
        flag_id = self._flag_ids.get(name)
        return flag_id is not None and flag_id // 8 < len(flags) and bool(flags[flag_id // 8] & (1 << (flag_id % 8)))