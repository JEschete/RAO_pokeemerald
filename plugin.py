from retroarch_overlay.core.contracts import GameContext

from .game.adapter import EmeraldAdapter
from .game.manifest import RA_GAME_ID


class PokeEmeraldPlugin:
    def create(self, context: GameContext) -> EmeraldAdapter:
        if context.repository_root is None:
            raise ValueError("Plugin repository root is required")
        decomp_root = context.settings.get(
            "pokeemerald.decomp_root",
            context.repository_root / "vendor" / "pokeemerald",
        )
        progress = (
            context.ra_progress_provider(RA_GAME_ID)
            if context.ra_progress_provider is not None
            else None
        )
        return EmeraldAdapter(decomp_root, progress)


PLUGIN = PokeEmeraldPlugin()
