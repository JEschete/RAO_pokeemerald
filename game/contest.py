from dataclasses import dataclass

from .state import PokemonState


POKEBLOCK_SIZE = 7
POKEBLOCK_COUNT = 40
POKEBLOCKS_SIZE = POKEBLOCK_SIZE * POKEBLOCK_COUNT
POKEBLOCK_COLORS = (
    "None", "Red", "Blue", "Pink", "Green", "Yellow", "Purple", "Indigo",
    "Brown", "Light Blue", "Olive", "Gray", "Black", "White", "Gold",
)
CONTEST_RIBBONS = ("Cool", "Beauty", "Cute", "Smart", "Tough")
SPECIAL_RIBBONS = (
    (15, "Champion"),
    (16, "Winning"),
    (17, "Victory"),
    (18, "Artist"),
    (19, "Effort"),
)


@dataclass(frozen=True, slots=True)
class PokeblockState:
    slot: int
    color: str
    spicy: int
    dry: int
    sweet: int
    bitter: int
    sour: int
    feel: int


def decode_pokeblocks(data: bytes) -> tuple[PokeblockState, ...]:
    if len(data) != POKEBLOCKS_SIZE:
        raise ValueError(
            f"Expected {POKEBLOCKS_SIZE} Pokeblock bytes, received {len(data)}"
        )
    result = []
    for slot in range(POKEBLOCK_COUNT):
        offset = slot * POKEBLOCK_SIZE
        color_id = data[offset]
        if color_id == 0:
            continue
        color = POKEBLOCK_COLORS[color_id] if color_id < len(POKEBLOCK_COLORS) else f"Color {color_id}"
        result.append(
            PokeblockState(slot, color, *data[offset + 1 : offset + 7])
        )
    return tuple(result)


def ribbon_names(member: PokemonState) -> tuple[str, ...]:
    names = []
    for index, category in enumerate(CONTEST_RIBBONS):
        rank = (member.ribbons >> (index * 3)) & 0x7
        if rank:
            names.append(f"{category} rank {rank}")
    names.extend(
        name for bit, name in SPECIAL_RIBBONS if member.ribbons & (1 << bit)
    )
    return tuple(names)