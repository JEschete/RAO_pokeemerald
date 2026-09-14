from dataclasses import dataclass


STAT_NAMES = ("HP", "Attack", "Defense", "Speed", "Sp. Atk", "Sp. Def")
CONTEST_NAMES = ("Cool", "Beauty", "Cute", "Smart", "Tough")
NATURE_NAMES = (
    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
    "Bold", "Docile", "Relaxed", "Impish", "Lax",
    "Timid", "Hasty", "Serious", "Jolly", "Naive",
    "Modest", "Mild", "Quiet", "Bashful", "Rash",
    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
)
SUBSTRUCT_ORDERS = (
    (0, 1, 2, 3), (0, 1, 3, 2), (0, 2, 1, 3), (0, 3, 1, 2),
    (0, 2, 3, 1), (0, 3, 2, 1), (1, 0, 2, 3), (1, 0, 3, 2),
    (2, 0, 1, 3), (3, 0, 1, 2), (2, 0, 3, 1), (3, 0, 2, 1),
    (1, 2, 0, 3), (1, 3, 0, 2), (2, 1, 0, 3), (3, 1, 0, 2),
    (2, 3, 0, 1), (3, 2, 0, 1), (1, 2, 3, 0), (1, 3, 2, 0),
    (2, 1, 3, 0), (3, 1, 2, 0), (2, 3, 1, 0), (3, 2, 1, 0),
)


@dataclass(frozen=True, slots=True)
class PokemonState:
    slot: int
    species_id: int
    species: str
    personality: int
    ot_id: int
    level: int
    experience: int
    held_item_id: int
    moves: tuple[int, int, int, int]
    pp: tuple[int, int, int, int]
    pp_bonuses: int
    friendship: int
    evs: tuple[int, int, int, int, int, int]
    contest: tuple[int, int, int, int, int]
    sheen: int
    pokerus: int
    ivs: tuple[int, int, int, int, int, int]
    is_egg: bool
    ability_slot: int
    ribbons: int
    status: int
    hp: int
    max_hp: int
    stats: tuple[int, int, int, int, int]
    is_traded: bool

    @property
    def nature_id(self) -> int:
        return self.personality % len(NATURE_NAMES)

    @property
    def nature(self) -> str:
        return NATURE_NAMES[self.nature_id]

    @property
    def pokerus_state(self) -> str:
        if self.pokerus == 0:
            return "None"
        days = self.pokerus & 0xF
        if days:
            return f"Active · {days} day(s)"
        return "Cured"

    @property
    def ribbon_count(self) -> int:
        contest_ribbons = sum((self.ribbons >> (index * 3)) & 0x7 for index in range(5))
        return contest_ribbons + (self.ribbons >> 15).bit_count()


@dataclass(frozen=True, slots=True)
class BattlePokemonState:
    species_id: int
    species: str
    level: int
    hp: int
    max_hp: int
    stats: tuple[int, int, int, int, int]
    moves: tuple[int, int, int, int]
    pp: tuple[int, int, int, int]
    ivs: tuple[int, int, int, int, int, int]
    stat_stages: tuple[int, int, int, int, int, int, int, int]
    ability_id: int
    ability_slot: int
    types: tuple[int, int]
    held_item_id: int
    friendship: int
    personality: int
    status: int


class InvalidPokemonData(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BoxPokemonState:
    species_id: int
    species: str
    personality: int
    ot_id: int
    experience: int
    held_item_id: int
    friendship: int
    is_egg: bool
    ability_slot: int
    ivs: tuple[int, int, int, int, int, int] = (0, 0, 0, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class StoredPokemonState:
    box: int
    slot: int
    pokemon: BoxPokemonState


def decode_party(
    data: bytes,
    count: int,
    species_by_id: dict[int, str],
    *,
    player_trainer_id: int | None = None,
) -> tuple[PokemonState, ...]:
    if not 0 <= count <= 6:
        raise InvalidPokemonData(f"Invalid party count: {count}")
    expected = count * 0x64
    if len(data) != expected:
        raise InvalidPokemonData(
            f"Expected {expected} party bytes for {count} Pokemon, received {len(data)}"
        )
    result = []
    for slot in range(count):
        raw = data[slot * 0x64 : (slot + 1) * 0x64]
        try:
            state = decode_pokemon(
                raw,
                slot,
                species_by_id,
                player_trainer_id=player_trainer_id,
            )
        except InvalidPokemonData:
            continue
        result.append(state)
    return tuple(result)


def decode_box_pokemon(
    raw: bytes,
    species_by_id: dict[int, str],
) -> BoxPokemonState | None:
    if len(raw) != 0x50:
        raise InvalidPokemonData(
            f"Box Pokemon record must be 80 bytes, received {len(raw)}"
        )
    personality = int.from_bytes(raw[0:4], "little")
    ot_id = int.from_bytes(raw[4:8], "little")
    secure = _decrypt_secure_data(raw[0x20:0x50], personality ^ ot_id)
    checksum = sum(
        int.from_bytes(secure[offset : offset + 2], "little")
        for offset in range(0, len(secure), 2)
    ) & 0xFFFF
    if checksum != int.from_bytes(raw[0x1C:0x1E], "little"):
        return None
    order = SUBSTRUCT_ORDERS[personality % 24]
    substructs = tuple(
        secure[position * 12 : (position + 1) * 12]
        for position in order
    )
    growth, _, _, misc = substructs
    species_id = int.from_bytes(growth[0:2], "little")
    species = species_by_id.get(species_id)
    if species_id == 0 or species is None:
        return None
    iv_word = int.from_bytes(misc[4:8], "little")
    return BoxPokemonState(
        species_id,
        species,
        personality,
        ot_id,
        int.from_bytes(growth[4:8], "little"),
        int.from_bytes(growth[2:4], "little"),
        growth[9],
        bool((iv_word >> 30) & 1),
        (iv_word >> 31) & 1,
        tuple((iv_word >> (index * 5)) & 0x1F for index in range(6)),
    )


def decode_pokemon_storage(
    data: bytes,
    species_by_id: dict[int, str],
    *,
    box_count: int = 14,
    slots_per_box: int = 30,
) -> tuple[StoredPokemonState, ...]:
    record_size = 0x50
    expected = box_count * slots_per_box * record_size
    if len(data) != expected:
        raise InvalidPokemonData(
            f"Expected {expected} Pokemon storage bytes, received {len(data)}"
        )
    result = []
    for index in range(box_count * slots_per_box):
        offset = index * record_size
        pokemon = decode_box_pokemon(
            data[offset : offset + record_size],
            species_by_id,
        )
        if pokemon is not None:
            result.append(
                StoredPokemonState(
                    box=index // slots_per_box + 1,
                    slot=index % slots_per_box + 1,
                    pokemon=pokemon,
                )
            )
    return tuple(result)


def decode_pokemon(
    raw: bytes,
    slot: int,
    species_by_id: dict[int, str],
    *,
    player_trainer_id: int | None = None,
) -> PokemonState:
    if len(raw) != 0x64:
        raise InvalidPokemonData(f"Pokemon record must be 100 bytes, received {len(raw)}")
    personality = int.from_bytes(raw[0:4], "little")
    ot_id = int.from_bytes(raw[4:8], "little")
    secure = _decrypt_secure_data(raw[0x20:0x50], personality ^ ot_id)
    checksum = sum(
        int.from_bytes(secure[offset : offset + 2], "little")
        for offset in range(0, len(secure), 2)
    ) & 0xFFFF
    if checksum != int.from_bytes(raw[0x1C:0x1E], "little"):
        raise InvalidPokemonData(f"Pokemon in slot {slot} has an invalid checksum")
    order = SUBSTRUCT_ORDERS[personality % 24]
    substructs = tuple(
        secure[position * 12 : (position + 1) * 12]
        for position in order
    )
    growth, attacks, effort, misc = substructs
    species_id = int.from_bytes(growth[0:2], "little")
    species = species_by_id.get(species_id)
    level = raw[0x54]
    if species is None or not 1 <= level <= 100:
        raise InvalidPokemonData(f"Pokemon in slot {slot} has invalid species or level")
    iv_word = int.from_bytes(misc[4:8], "little")
    ivs = tuple((iv_word >> (index * 5)) & 0x1F for index in range(6))
    return PokemonState(
        slot=slot,
        species_id=species_id,
        species=species,
        personality=personality,
        ot_id=ot_id,
        level=level,
        experience=int.from_bytes(growth[4:8], "little"),
        held_item_id=int.from_bytes(growth[2:4], "little"),
        moves=tuple(
            int.from_bytes(attacks[index * 2 : index * 2 + 2], "little")
            for index in range(4)
        ),
        pp=tuple(attacks[8:12]),
        pp_bonuses=growth[8],
        friendship=growth[9],
        evs=tuple(effort[0:6]),
        contest=tuple(effort[6:11]),
        sheen=effort[11],
        pokerus=misc[0],
        ivs=ivs,
        is_egg=bool((iv_word >> 30) & 1),
        ability_slot=(iv_word >> 31) & 1,
        ribbons=int.from_bytes(misc[8:12], "little"),
        status=int.from_bytes(raw[0x50:0x54], "little"),
        hp=int.from_bytes(raw[0x56:0x58], "little"),
        max_hp=int.from_bytes(raw[0x58:0x5A], "little"),
        stats=tuple(
            int.from_bytes(raw[offset : offset + 2], "little")
            for offset in (0x5A, 0x5C, 0x5E, 0x60, 0x62)
        ),
        is_traded=player_trainer_id is not None and ot_id != player_trainer_id,
    )


def _decrypt_secure_data(data: bytes, key: int) -> bytes:
    if len(data) != 48:
        raise InvalidPokemonData(f"Secure Pokemon data must be 48 bytes, received {len(data)}")
    return b"".join(
        (int.from_bytes(data[offset : offset + 4], "little") ^ key).to_bytes(
            4, "little"
        )
        for offset in range(0, len(data), 4)
    )


def decode_battle_pokemon(
    raw: bytes, species_by_id: dict[int, str]
) -> BattlePokemonState | None:
    if len(raw) != 0x58:
        raise InvalidPokemonData(
            f"Battle Pokemon record must be 88 bytes, received {len(raw)}"
        )
    species_id = int.from_bytes(raw[0:2], "little")
    species = species_by_id.get(species_id)
    level = raw[0x2A]
    hp = int.from_bytes(raw[0x28:0x2A], "little")
    max_hp = int.from_bytes(raw[0x2C:0x2E], "little")
    if species is None or not 1 <= level <= 100 or hp > max_hp or max_hp == 0:
        return None
    iv_word = int.from_bytes(raw[0x14:0x18], "little")
    return BattlePokemonState(
        species_id=species_id,
        species=species,
        level=level,
        hp=hp,
        max_hp=max_hp,
        stats=tuple(
            int.from_bytes(raw[offset : offset + 2], "little")
            for offset in (0x02, 0x04, 0x06, 0x08, 0x0A)
        ),
        moves=tuple(
            int.from_bytes(raw[offset : offset + 2], "little")
            for offset in (0x0C, 0x0E, 0x10, 0x12)
        ),
        pp=tuple(raw[0x24:0x28]),
        ivs=tuple((iv_word >> (index * 5)) & 0x1F for index in range(6)),
        stat_stages=tuple(raw[0x18:0x20]),
        ability_id=raw[0x20],
        ability_slot=(iv_word >> 31) & 1,
        types=(raw[0x21], raw[0x22]),
        held_item_id=int.from_bytes(raw[0x2E:0x30], "little"),
        friendship=raw[0x2B],
        personality=int.from_bytes(raw[0x48:0x4C], "little"),
        status=int.from_bytes(raw[0x4C:0x50], "little"),
    )