from dataclasses import dataclass

from retroarch_overlay.core.contracts import MemoryReader
from retroarch_overlay.retroarch import RetroArchError


SAVE_BLOCK_1_POINTER = 0x03005D8C
SAVE_BLOCK_2_POINTER = 0x03005D90
EWRAM_START = 0x02000000
EWRAM_END = 0x02040000


@dataclass(frozen=True, slots=True)
class SavePointers:
    block_1: int
    block_2: int


def read_save_pointers(memory: MemoryReader, *, allow_empty: bool = False) -> SavePointers:
    block_1 = int.from_bytes(memory.read_memory(SAVE_BLOCK_1_POINTER, 4), "little")
    block_2 = int.from_bytes(memory.read_memory(SAVE_BLOCK_2_POINTER, 4), "little")
    if allow_empty and block_1 == 0:
        return SavePointers(0, block_2)
    for label, pointer in (("1", block_1), ("2", block_2)):
        if not EWRAM_START <= pointer < EWRAM_END:
            raise RetroArchError(
                f"Invalid Emerald save block {label} pointer: 0x{pointer:08X}"
            )
    return SavePointers(block_1, block_2)


def verify_save_pointers(memory: MemoryReader, expected: SavePointers) -> None:
    current = read_save_pointers(memory, allow_empty=True)
    if current != expected:
        raise RetroArchError("Emerald save blocks changed while building the snapshot")