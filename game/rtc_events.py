from dataclasses import dataclass

from retroarch_overlay.core.contracts import MemoryReader
from retroarch_overlay.models import PanelAction, PanelRow, PanelSection

from .state import PokemonState


BERRY_TREES_OFFSET = 0x169C
BERRY_TREE_SIZE = 8
BERRY_TREE_COUNT = 128
BERRY_TREES_SIZE = BERRY_TREE_SIZE * BERRY_TREE_COUNT
OUTBREAK_OFFSET = 0x2B90
OUTBREAK_SIZE = 0x14
VARS_OFFSET = 0x139C
VARS_START = 0x4000
LAST_TIME_UPDATE_OFFSET = 0xA0
TIME_SIZE = 8

DAILY_REWARDS = (
    ("FLAG_DAILY_CONTEST_LOBBY_RECEIVED_BERRY", "Contest lobby berry"),
    ("FLAG_DAILY_PICKED_LOTO_TICKET", "Lilycove lottery ticket"),
    ("FLAG_DAILY_ROUTE_114_RECEIVED_BERRY", "Route 114 berry"),
    ("FLAG_DAILY_ROUTE_111_RECEIVED_BERRY", "Route 111 berry"),
    ("FLAG_DAILY_BERRY_MASTER_RECEIVED_BERRY", "Berry Master gift"),
    ("FLAG_DAILY_ROUTE_120_RECEIVED_BERRY", "Route 120 berry"),
    ("FLAG_DAILY_LILYCOVE_RECEIVED_BERRY", "Lilycove berry"),
    ("FLAG_DAILY_FLOWER_SHOP_RECEIVED_BERRY", "Flower Shop berry"),
    ("FLAG_DAILY_BERRY_MASTERS_WIFE", "Berry Master's wife phrase"),
    ("FLAG_DAILY_SOOTOPOLIS_RECEIVED_BERRY", "Sootopolis berry"),
)


@dataclass(frozen=True, slots=True)
class BerryTreeState:
    tree_id: int
    berry_id: int
    stage: int
    minutes: int
    yield_count: int
    watered: int


class RtcEventDashboard:
    def __init__(
        self,
        flag_ids: dict[str, int],
        variable_ids: dict[str, int],
        species_by_id: dict[int, str],
        item_names: dict[int, str],
        map_names: dict[tuple[int, int], str],
    ) -> None:
        self._flag_ids = flag_ids
        self._variable_ids = variable_ids
        self._species_by_id = species_by_id
        self._item_names = item_names
        self._map_names = map_names
        self._first_berry_item = next(
            (item_id for item_id, name in item_names.items() if name == "Cheri Berry"),
            133,
        )

    def section(
        self,
        memory: MemoryReader,
        save_block_1: int,
        save_block_2: int,
        flags: bytes,
        party: tuple[PokemonState, ...],
    ) -> PanelSection:
        trees = self._berry_trees(
            memory.read_memory(save_block_1 + BERRY_TREES_OFFSET, BERRY_TREES_SIZE)
        )
        ready = [tree for tree in trees if tree.stage == 5]
        growing = [tree for tree in trees if tree.stage in {1, 2, 3, 4}]
        outbreak = memory.read_memory(save_block_1 + OUTBREAK_OFFSET, OUTBREAK_SIZE)
        outbreak_species = int.from_bytes(outbreak[0:2], "little")
        daily_available = [
            label for flag, label in DAILY_REWARDS if not self._flag(flags, flag)
        ]
        mirage = self._variable(memory, save_block_1, "VAR_MIRAGE_RND_H")
        mirage_match = next(
            (member for member in party if member.personality & 0xFFFF == mirage),
            None,
        )
        lottery = self._variable(memory, save_block_1, "VAR_POKELOT_RND1")
        last_update = memory.read_memory(
            save_block_2 + LAST_TIME_UPDATE_OFFSET, TIME_SIZE
        )
        days = int.from_bytes(last_update[0:2], "little", signed=True)
        hours = int.from_bytes(last_update[2:3], "little", signed=True)
        minutes = int.from_bytes(last_update[3:4], "little", signed=True)
        tide = "High" if self._flag(flags, "FLAG_SYS_SHOAL_TIDE") else "Low"

        rows = (
            PanelRow(f"Berries · {len(ready)} ready · {len(growing)} growing"),
            PanelRow(
                f"Daily rewards · {len(daily_available)} available · "
                f"Shoal tide {tide.lower()}"
            ),
        )
        details = [
            PanelRow("GAME TIME EVENTS"),
            PanelRow(
                f"Last processed · day {days} · {hours % 24:02d}:{minutes % 60:02d}"
            ),
            PanelRow(f"Shoal Cave · {tide} tide"),
            PanelRow(
                f"Mirage Island · {'PRESENT via ' + self._name(mirage_match.species) if mirage_match else f'no party match for {mirage:04X}'}"
            ),
            PanelRow(f"Lilycove lottery · {lottery:05d}"),
        ]
        if outbreak_species:
            map_name = self._map_names.get(
                (outbreak[3], outbreak[2]),
                f"Map {outbreak[3]}:{outbreak[2]}",
            )
            species = self._species_by_id.get(
                outbreak_species, f"SPECIES_{outbreak_species}"
            )
            details.append(
                PanelRow(
                    f"Outbreak · {self._name(species)} · Lv {outbreak[4]} · "
                    f"{map_name} · {outbreak[0x11]}% · {int.from_bytes(outbreak[0x12:0x14], 'little')} day(s)"
                )
            )
        else:
            details.append(PanelRow("Outbreak · none active"))
        details.append(PanelRow("DAILY REWARDS AVAILABLE"))
        details.extend(
            PanelRow(label, False) for label in daily_available
        )
        if not daily_available:
            details.append(PanelRow("All tracked daily rewards collected", True))
        details.append(PanelRow("BERRY TREES"))
        for tree in sorted(trees, key=lambda value: (value.stage != 5, value.minutes, value.tree_id))[:40]:
            berry_name = self._item_names.get(
                self._first_berry_item + tree.berry_id - 1,
                f"Berry {tree.berry_id}",
            )
            stage = {
                1: "planted",
                2: "sprouted",
                3: "growing",
                4: "flowering",
                5: f"ready x{tree.yield_count}",
                255: "sparkling",
            }.get(tree.stage, f"stage {tree.stage}")
            details.append(
                PanelRow(
                    f"Tree {tree.tree_id} · {berry_name} · {stage} · "
                    f"{tree.minutes}m · watered {tree.watered}/4"
                )
            )
        return PanelSection(
            "World events",
            rows,
            actions=(PanelAction("OPEN WORLD EVENTS", "RTC and World Events", tuple(details)),),
            priority=30,
            role="goals",
            compact_rows=(rows[0],),
        )

    @staticmethod
    def _berry_trees(data: bytes) -> tuple[BerryTreeState, ...]:
        if len(data) != BERRY_TREES_SIZE:
            raise ValueError(
                f"Expected {BERRY_TREES_SIZE} berry-tree bytes, received {len(data)}"
            )
        result = []
        for tree_id in range(BERRY_TREE_COUNT):
            offset = tree_id * BERRY_TREE_SIZE
            berry_id = data[offset]
            if not berry_id:
                continue
            flags = data[offset + 5]
            result.append(
                BerryTreeState(
                    tree_id,
                    berry_id,
                    data[offset + 1] & 0x7F,
                    int.from_bytes(data[offset + 2 : offset + 4], "little"),
                    data[offset + 4],
                    sum(bool(flags & mask) for mask in (0x10, 0x20, 0x40, 0x80)),
                )
            )
        return tuple(result)

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

    @staticmethod
    def _name(species: str) -> str:
        return " ".join(word.capitalize() for word in species.removeprefix("SPECIES_").split("_"))