import tempfile
import unittest
from pathlib import Path

from game.icons import SpeciesIconCache

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POKEEMERALD_ROOT = PROJECT_ROOT / "decomp_reference" / "pokeemerald"
requires_pokeemerald = unittest.skipUnless(
    (POKEEMERALD_ROOT / "graphics" / "pokemon" / "treecko" / "icon.png").is_file(),
    "The pokeemerald decomp reference is unavailable",
)


class RecordingRenderer:
    """Stands in for the Pillow renderer without importing an image library."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path]] = []

    def __call__(self, source: Path, target: Path) -> Path:
        self.calls.append((source, target))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"png")
        return target


def decomp_with(*folders: str) -> tempfile.TemporaryDirectory:
    directory = tempfile.TemporaryDirectory()
    for folder in folders:
        path = Path(directory.name) / "graphics" / "pokemon" / folder
        path.mkdir(parents=True, exist_ok=True)
        (path / "icon.png").write_bytes(b"source")
    return directory


class SpeciesIconCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._decomp = decomp_with("treecko", "unown/a")
        self._state = tempfile.TemporaryDirectory()
        self.renderer = RecordingRenderer()
        self.cache = SpeciesIconCache(
            Path(self._decomp.name), Path(self._state.name), self.renderer
        )

    def tearDown(self) -> None:
        self._decomp.cleanup()
        self._state.cleanup()

    def test_renders_once_and_memoizes_the_path(self) -> None:
        first = self.cache.path_for("SPECIES_TREECKO")
        second = self.cache.path_for("SPECIES_TREECKO")

        self.assertTrue(first.endswith("treecko.png"))
        self.assertEqual(first, second)
        self.assertEqual(len(self.renderer.calls), 1)

    def test_existing_cache_file_is_reused_without_rendering(self) -> None:
        icons = Path(self._state.name) / "icons"
        icons.mkdir(parents=True, exist_ok=True)
        (icons / "treecko.png").write_bytes(b"stale-but-present")

        path = self.cache.path_for("SPECIES_TREECKO")

        self.assertTrue(path.endswith("treecko.png"))
        self.assertEqual(self.renderer.calls, [])

    def test_unown_falls_back_to_its_letter_subfolder(self) -> None:
        self.assertTrue(self.cache.path_for("SPECIES_UNOWN").endswith("unown.png"))
        source, _ = self.renderer.calls[0]
        self.assertEqual(source.parent.name, "a")

    def test_species_without_artwork_is_skipped(self) -> None:
        self.assertEqual(self.cache.path_for("SPECIES_MISSINGNO"), "")
        self.assertEqual(self.renderer.calls, [])

    def test_a_failing_renderer_disables_that_icon(self) -> None:
        def explode(source: Path, target: Path) -> Path:
            raise OSError("disk full")

        cache = SpeciesIconCache(
            Path(self._decomp.name), Path(self._state.name), explode
        )

        self.assertEqual(cache.path_for("SPECIES_TREECKO"), "")

    def test_icons_are_disabled_without_a_renderer_or_state_directory(self) -> None:
        without_renderer = SpeciesIconCache(
            Path(self._decomp.name), Path(self._state.name), None
        )
        without_state = SpeciesIconCache(
            Path(self._decomp.name), None, self.renderer
        )

        self.assertEqual(without_renderer.path_for("SPECIES_TREECKO"), "")
        self.assertEqual(without_state.path_for("SPECIES_TREECKO"), "")
        self.assertEqual(self.renderer.calls, [])


@requires_pokeemerald
class IconRendererTests(unittest.TestCase):
    def test_real_sheet_renders_a_square_bottom_aligned_icon(self) -> None:
        from PIL import Image

        from icon_renderer import ICON_SIZE, render_icon

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "treecko.png"
            render_icon(
                POKEEMERALD_ROOT / "graphics" / "pokemon" / "treecko" / "icon.png",
                target,
            )
            with Image.open(target) as icon:
                self.assertEqual(icon.size, (ICON_SIZE, ICON_SIZE))
                self.assertEqual(icon.mode, "RGBA")
                # The sprite is bottom-aligned, so the last row carries pixels.
                opaque_rows = {
                    y
                    for x in range(ICON_SIZE)
                    for y in range(ICON_SIZE)
                    if icon.getpixel((x, y))[3]
                }
                self.assertIn(ICON_SIZE - 1, opaque_rows)


if __name__ == "__main__":
    unittest.main()
