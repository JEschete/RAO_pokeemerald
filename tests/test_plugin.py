import unittest
from pathlib import Path

from retroarch_overlay.core.contracts import GameContext
from retroarch_overlay.infrastructure.plugin_discovery import parse_plugin_manifest
from retroarch_overlay.infrastructure.plugin_discovery import DiscoveredPluginRepository
from retroarch_overlay.infrastructure.plugin_loader import RepositoryAdapter


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class PluginContractTests(unittest.TestCase):
    def test_factory_uses_pinned_pokeemerald_submodule(self) -> None:
        repository = DiscoveredPluginRepository(
            REPOSITORY_ROOT,
            parse_plugin_manifest(REPOSITORY_ROOT),
        )
        adapter = RepositoryAdapter(
            repository,
            GameContext(repository_root=REPOSITORY_ROOT),
        )._load_adapter()

        self.assertEqual(type(adapter).__name__, "EmeraldAdapter")
        self.assertEqual(adapter.name, "Pokémon Emerald")
        self.assertTrue(type(adapter).__module__.startswith("_retroarch_overlay_plugin_"))


if __name__ == "__main__":
    unittest.main()