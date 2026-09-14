"""Cached species mini-icon paths for panel rows.

The Pillow work lives in the plugin's icon_renderer module and is injected,
so this layer stays free of image-library imports. A missing renderer,
decomp file or write failure simply disables icons.
"""

from collections import OrderedDict
from pathlib import Path


class SpeciesIconCache:
    def __init__(
        self,
        decomp_root: Path,
        state_directory: Path | None,
        render_icon=None,
        maximum_entries: int = 128,
    ) -> None:
        if maximum_entries <= 0:
            raise ValueError("Species icon cache size must be positive")
        self._decomp_root = decomp_root
        self._directory = (
            state_directory / "icons" if state_directory is not None else None
        )
        self._render_icon = render_icon
        self.maximum_entries = maximum_entries
        self._paths: OrderedDict[str, str] = OrderedDict()

    @property
    def size(self) -> int:
        return len(self._paths)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self._paths)

    def path_for(self, species: str) -> str:
        cached = self._paths.pop(species, None)
        if cached is not None:
            self._paths[species] = cached
            return cached
        path = self._render(species)
        self._paths[species] = path
        while len(self._paths) > self.maximum_entries:
            self._paths.popitem(last=False)
        return path

    def _render(self, species: str) -> str:
        if self._directory is None or self._render_icon is None:
            return ""
        folder = species.removeprefix("SPECIES_").lower()
        target = self._directory / f"{folder}.png"
        if target.is_file():
            return str(target)
        source = self._source(folder)
        if source is None:
            return ""
        try:
            self._render_icon(source, target)
        except (OSError, ValueError):
            return ""
        return str(target)

    def _source(self, folder: str) -> Path | None:
        base = self._decomp_root / "graphics" / "pokemon" / folder
        # Unown keeps per-letter subfolders; fall back to its A form.
        for candidate in (base / "icon.png", base / "a" / "icon.png"):
            if candidate.is_file():
                return candidate
        return None
