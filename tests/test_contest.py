import unittest

from game.contest import POKEBLOCKS_SIZE, decode_pokeblocks


class ContestStateTests(unittest.TestCase):
    def test_decodes_pokeblock_color_flavors_and_feel(self) -> None:
        data = bytearray(POKEBLOCKS_SIZE)
        data[0:7] = bytes((2, 10, 20, 30, 40, 50, 60))

        blocks = decode_pokeblocks(bytes(data))

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].color, "Blue")
        self.assertEqual(
            (blocks[0].spicy, blocks[0].dry, blocks[0].sweet, blocks[0].bitter, blocks[0].sour, blocks[0].feel),
            (10, 20, 30, 40, 50, 60),
        )


if __name__ == "__main__":
    unittest.main()