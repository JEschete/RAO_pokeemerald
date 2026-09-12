"""Precompute Emerald map/marker data so the runtime never parses the decomp.

Parsing the ~1100 decompilation files costs about a minute when the plugin lives
on a network share, which stalls the overlay's first connection. Mirrors the
knowledge_builder.py / emerald_knowledge.json arrangement.

    python -m game.map_builder [decomp_root] [output]
"""

import json
import sys
from pathlib import Path

from .knowledge_builder import SOURCE_REVISION
from .mapdata import MAP_SCHEMA_VERSION, EmeraldMapCatalog


DEFAULT_OUTPUT = Path(__file__).resolve().parent / "data" / "emerald_map.json"


def build_map_data(decomp_root: Path) -> dict:
    return EmeraldMapCatalog(decomp_root).to_document(SOURCE_REVISION)


def write_map_data(decomp_root: Path, output: Path = DEFAULT_OUTPUT) -> Path:
    document = build_map_data(decomp_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, separators=(",", ":")), encoding="utf-8"
    )
    return output


def load_map_catalog(
    decomp_root: Path, path: Path = DEFAULT_OUTPUT
) -> EmeraldMapCatalog:
    """Load the precomputed catalog, falling back to parsing the decomp."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return EmeraldMapCatalog(decomp_root)
    try:
        return EmeraldMapCatalog.from_document(
            decomp_root, document, SOURCE_REVISION
        )
    except (ValueError, TypeError):
        return EmeraldMapCatalog(decomp_root)


def main(argv: list[str]) -> int:
    root = (
        Path(argv[0])
        if argv
        else Path(__file__).resolve().parents[1] / "decomp_reference" / "pokeemerald"
    )
    output = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUTPUT
    written = write_map_data(root, output)
    size = written.stat().st_size
    print(f"schema {MAP_SCHEMA_VERSION} revision {SOURCE_REVISION[:12]}")
    print(f"wrote {written} ({size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
