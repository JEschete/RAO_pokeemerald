from pathlib import Path

from retroarch_overlay.core.contracts import GameContext
from retroarch_overlay.models import MapDocument, MapLayer

from .game.adapter import EmeraldAdapter
from .game.manifest import RA_GAME_ID
from .game.map_builder import load_map_catalog
from .game.mapdata import MAP_KINDS, EmeraldMapCatalog, EmeraldMapImages
from .game.worldmap import (
    KIND_REGION,
    REGION_COLS,
    REGION_ROWS,
    REGION_TILE,
)


class PokeEmeraldPlugin:
    def create(self, context: GameContext) -> EmeraldAdapter:
        if context.repository_root is None:
            raise ValueError("Plugin repository root is required")
        decomp_root = Path(
            context.settings.get(
                "pokeemerald.decomp_root",
                context.repository_root / "decomp_reference" / "pokeemerald",
            )
        )
        progress = (
            context.ra_progress_provider(RA_GAME_ID)
            if context.ra_progress_provider is not None
            else None
        )
        catalog, document = self._map_assets(decomp_root, context.state_directory)
        return EmeraldAdapter(
            decomp_root,
            progress,
            context.state_directory,
            catalog,
            document,
            self._icon_renderer(),
        )

    @staticmethod
    def _icon_renderer():
        """Party sprites are optional: without Pillow the rail omits them."""
        try:
            from .icon_renderer import render_icon
        except ImportError:
            return None
        return render_icon

    @staticmethod
    def _map_assets(
        decomp_root: Path, state_directory: Path | None
    ) -> tuple[EmeraldMapCatalog | None, MapDocument | None]:
        """Maps are optional: a missing decomp, cache or Pillow just hides them."""
        if state_directory is None:
            return None, None
        try:
            from .map_renderer import load_tileset, render_layout
        except ImportError:
            return None, None
        try:
            catalog = load_map_catalog(decomp_root)
            images = EmeraldMapImages(
                catalog,
                decomp_root,
                state_directory,
                load_tileset,
                render_layout,
            )
            layers = images.layers()
        except (OSError, ValueError, KeyError):
            return None, None
        if not layers:
            return catalog, None
        world = PokeEmeraldPlugin._world_layer(decomp_root, state_directory)
        if world is not None:
            layers = (world,) + layers
        return catalog, MapDocument(
            "Pokemon Emerald", layers, MAP_KINDS + (KIND_REGION,)
        )

    @staticmethod
    def _world_layer(decomp_root: Path, state_directory: Path) -> MapLayer | None:
        """The Hoenn region map, selectable alongside the per-map layers."""
        try:
            from .map_renderer import render_region_map
        except ImportError:
            return None
        scale = 3
        image = state_directory / "maps" / "hoenn.png"
        return MapLayer(
            "hoenn",
            "Hoenn",
            "Hoenn",
            image,
            credit="Region map rendered locally from the pokeemerald decompilation",
            tile_width=REGION_TILE * scale,
            tile_height=REGION_TILE * scale,
            wrap_width=REGION_COLS,
            wrap_height=REGION_ROWS,
            anchor_x=REGION_TILE * scale // 2,
            anchor_y=REGION_TILE * scale // 2,
            image_loader=lambda: render_region_map(decomp_root, image, scale),
        )


PLUGIN = PokeEmeraldPlugin()
