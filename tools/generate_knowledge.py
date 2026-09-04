import argparse
import json
import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from game.knowledge_builder import SOURCE_REVISION, build_knowledge


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate pinned Pokemon Emerald knowledge")
    parser.add_argument(
        "--decomp-root",
        type=Path,
        default=PLUGIN_ROOT / "decomp_reference" / "pokeemerald",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PLUGIN_ROOT / "game" / "data" / "emerald_knowledge.json",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if (args.decomp_root / ".git").exists():
        try:
            result = subprocess.run(
                ("git", "-C", str(args.decomp_root), "rev-parse", "HEAD"),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            print(f"Could not verify decomp revision: {error}", file=sys.stderr)
            return 2
        actual_revision = result.stdout.strip().casefold()
        if result.returncode or actual_revision != SOURCE_REVISION.casefold():
            print(
                f"Decomp revision is {actual_revision or 'unknown'}; "
                f"expected {SOURCE_REVISION}",
                file=sys.stderr,
            )
            return 2
    rendered = json.dumps(
        build_knowledge(args.decomp_root),
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
    ) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            print(f"Generated knowledge is stale: {args.output}", file=sys.stderr)
            return 1
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())