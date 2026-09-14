import unittest

from game.state import (
    NATURE_NAMES,
    SUBSTRUCT_ORDERS,
    decode_box_pokemon,
    decode_party,
    decode_pokemon_storage,
)


def box_record(
    species_id: int,
    ivs: tuple[int, int, int, int, int, int],
    *,
    personality: int = 0,
    ot_id: int = 0x12345678,
) -> bytes:
    logical = [bytearray(12) for _ in range(4)]
    logical[0][0:2] = species_id.to_bytes(2, "little")
    iv_word = sum(value << (index * 5) for index, value in enumerate(ivs))
    logical[3][4:8] = iv_word.to_bytes(4, "little")
    physical = [bytearray(12) for _ in range(4)]
    for logical_index, physical_index in enumerate(
        SUBSTRUCT_ORDERS[personality % 24]
    ):
        physical[physical_index] = logical[logical_index]
    secure = b"".join(physical)
    checksum = sum(
        int.from_bytes(secure[offset : offset + 2], "little")
        for offset in range(0, 48, 2)
    ) & 0xFFFF
    key = personality ^ ot_id
    encrypted = b"".join(
        (int.from_bytes(secure[offset : offset + 4], "little") ^ key).to_bytes(
            4,
            "little",
        )
        for offset in range(0, 48, 4)
    )
    raw = bytearray(80)
    raw[0:4] = personality.to_bytes(4, "little")
    raw[4:8] = ot_id.to_bytes(4, "little")
    raw[0x1C:0x1E] = checksum.to_bytes(2, "little")
    raw[0x20:0x50] = encrypted
    return bytes(raw)


class PokemonStateTests(unittest.TestCase):
    def test_box_decoder_exposes_ivs(self) -> None:
        member = decode_box_pokemon(
            box_record(25, (31, 30, 29, 28, 27, 26)),
            {25: "SPECIES_PIKACHU"},
        )

        self.assertIsNotNone(member)
        assert member is not None
        self.assertEqual(member.ivs, (31, 30, 29, 28, 27, 26))

    def test_storage_decoder_tracks_box_and_slot_and_skips_bad_checksums(self) -> None:
        storage = bytearray(2 * 30 * 80)
        storage[(30 + 2) * 80 : (30 + 3) * 80] = box_record(
            25,
            (1, 2, 3, 4, 5, 6),
        )
        corrupt = bytearray(box_record(25, (31,) * 6))
        corrupt[0x1C] ^= 0xFF
        storage[5 * 80 : 6 * 80] = corrupt

        decoded = decode_pokemon_storage(
            bytes(storage),
            {25: "SPECIES_PIKACHU"},
            box_count=2,
        )

        self.assertEqual(len(decoded), 1)
        self.assertEqual((decoded[0].box, decoded[0].slot), (2, 3))
        self.assertEqual(decoded[0].pokemon.ivs, (1, 2, 3, 4, 5, 6))

    def test_decodes_all_encrypted_substructures_in_personality_order(self) -> None:
        personality = 23
        ot_id = 0x12345678
        logical = [bytearray(12) for _ in range(4)]
        logical[0][0:2] = (25).to_bytes(2, "little")
        logical[0][2:4] = (219).to_bytes(2, "little")
        logical[0][4:8] = (125000).to_bytes(4, "little")
        logical[0][8:10] = bytes((0b01010101, 220))
        for index, move in enumerate((33, 85, 98, 237)):
            logical[1][index * 2 : index * 2 + 2] = move.to_bytes(2, "little")
        logical[1][8:12] = bytes((35, 15, 30, 20))
        logical[2][:] = bytes((10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120))
        logical[3][0] = 0x21
        iv_word = sum(value << (index * 5) for index, value in enumerate((1, 2, 3, 4, 5, 6)))
        iv_word |= 1 << 31
        logical[3][4:8] = iv_word.to_bytes(4, "little")
        logical[3][8:12] = (0x12345678).to_bytes(4, "little")
        physical = [bytearray(12) for _ in range(4)]
        for logical_index, physical_index in enumerate(SUBSTRUCT_ORDERS[personality % 24]):
            physical[physical_index] = logical[logical_index]
        secure = b"".join(physical)
        checksum = sum(
            int.from_bytes(secure[offset : offset + 2], "little")
            for offset in range(0, 48, 2)
        ) & 0xFFFF
        key = personality ^ ot_id
        encrypted = b"".join(
            (int.from_bytes(secure[offset : offset + 4], "little") ^ key).to_bytes(4, "little")
            for offset in range(0, 48, 4)
        )
        raw = bytearray(100)
        raw[0:4] = personality.to_bytes(4, "little")
        raw[4:8] = ot_id.to_bytes(4, "little")
        raw[0x1C:0x1E] = checksum.to_bytes(2, "little")
        raw[0x20:0x50] = encrypted
        raw[0x50:0x54] = (0x40).to_bytes(4, "little")
        raw[0x54] = 50
        raw[0x56:0x58] = (120).to_bytes(2, "little")
        raw[0x58:0x5A] = (150).to_bytes(2, "little")
        for offset, value in zip((0x5A, 0x5C, 0x5E, 0x60, 0x62), (90, 80, 110, 100, 95)):
            raw[offset : offset + 2] = value.to_bytes(2, "little")

        member = decode_party(
            bytes(raw), 1, {25: "SPECIES_PIKACHU"}, player_trainer_id=1
        )[0]

        self.assertEqual(member.nature, NATURE_NAMES[23])
        self.assertEqual(member.held_item_id, 219)
        self.assertEqual(member.moves, (33, 85, 98, 237))
        self.assertEqual(member.pp, (35, 15, 30, 20))
        self.assertEqual(member.friendship, 220)
        self.assertEqual(member.evs, (10, 20, 30, 40, 50, 60))
        self.assertEqual(member.contest, (70, 80, 90, 100, 110))
        self.assertEqual(member.sheen, 120)
        self.assertEqual(member.pokerus_state, "Active · 1 day(s)")
        self.assertEqual(member.ivs, (1, 2, 3, 4, 5, 6))
        self.assertEqual(member.ability_slot, 1)
        self.assertEqual(member.ribbons, 0x12345678)
        self.assertEqual((member.hp, member.max_hp), (120, 150))
        self.assertEqual(member.stats, (90, 80, 110, 100, 95))
        self.assertTrue(member.is_traded)


if __name__ == "__main__":
    unittest.main()