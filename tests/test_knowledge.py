import unittest
from pathlib import Path

from game.knowledge import EmeraldKnowledge


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class EmeraldKnowledgeTests(unittest.TestCase):
    def test_generated_knowledge_contains_verified_mechanics(self) -> None:
        knowledge = EmeraldKnowledge.load(
            PLUGIN_ROOT / "game" / "data" / "emerald_knowledge.json"
        )

        zigzagoon = knowledge["species"]["SPECIES_ZIGZAGOON"]
        self.assertEqual(zigzagoon["ev_yield"], [0, 0, 0, 1, 0, 0])
        self.assertEqual(zigzagoon["abilities"][0], 53)
        self.assertEqual(knowledge["items"]["197"], "Lucky Egg")
        self.assertGreaterEqual(len(knowledge["trainers"]), 850)
        self.assertEqual(len(knowledge["moves"]), 355)


if __name__ == "__main__":
    unittest.main()