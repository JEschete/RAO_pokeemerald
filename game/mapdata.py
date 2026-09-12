import json
import re
from dataclasses import replace
from dataclasses import dataclass
from pathlib import Path


TRAINER_FLAGS_START = 0x500
MAP_SCHEMA_VERSION = 4

DEFINE_PATTERN = re.compile(r"^#define\s+([A-Z0-9_]+)\s+(.+?)\s*(?://.*)?$", re.MULTILINE)
LABEL_PATTERN = re.compile(r"^([A-Za-z0-9_]+)::")
TRAINER_BATTLE_PATTERN = re.compile(r"\btrainerbattle\w*\s+(.*)$")
TRADE_PATTERN = re.compile(r"CreateInGameTradePokemon|DoInGameTradeScene")
OUTDOOR_MAP_TYPES = frozenset(
    {
        "MAP_TYPE_TOWN",
        "MAP_TYPE_CITY",
        "MAP_TYPE_ROUTE",
        "MAP_TYPE_OCEAN_ROUTE",
        "MAP_TYPE_UNDERWATER",
    }
)
GIVE_ITEM_PATTERN = re.compile(r"\bgiveitem\w*\s+(ITEM_[A-Z0-9_]+)")
SET_FLAG_PATTERN = re.compile(r"\bsetflag\s+(FLAG_[A-Z0-9_]+)")
TRAINER_TOKEN_PATTERN = re.compile(r"\bTRAINER_[A-Z0-9_]+")
FIND_ITEM_PATTERN = re.compile(r"\b(?:finditem|giveitem\w*)\s+(ITEM_[A-Z0-9_]+)")
REMATCH_PATTERN = re.compile(
    r"\[REMATCH_[A-Z0-9_]+\]\s*=\s*REMATCH\(([^)]*)\)", re.MULTILINE
)


@dataclass(frozen=True, slots=True)
class MapMarker:
    x: int
    y: int
    kind: str
    marker: str
    title: str
    detail: str = ""
    flag: int | None = None
    flags: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class EmeraldMapEntry:
    map_id: str
    name: str
    group: int
    number: int
    layout_id: str
    markers: tuple[MapMarker, ...]
    map_type: str = ""
    region_section: str = ""

    @property
    def key(self) -> str:
        return self.map_id.removeprefix("MAP_").lower()

    @property
    def numeric_id(self) -> int:
        return self.group * 256 + self.number


@dataclass(frozen=True, slots=True)
class LayoutSpec:
    layout_id: str
    width: int
    height: int
    primary: str
    secondary: str
    blockdata: str


def _strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def parse_defines(path: Path) -> dict[str, int]:
    """Resolve `#define NAME 0x1F4` and `#define NAME (OTHER + 0x05)` forms."""
    raw: dict[str, str] = {}
    for name, value in DEFINE_PATTERN.findall(_strip_comments(path.read_text(encoding="utf-8"))):
        raw[name] = value.strip()
    resolved: dict[str, int] = {}

    def resolve(name: str, depth: int = 0) -> int | None:
        if name in resolved:
            return resolved[name]
        if depth > 8 or name not in raw:
            return None
        expression = raw[name].strip("()").strip()
        total = 0
        for token in re.split(r"\s*\+\s*", expression):
            token = token.strip()
            if not token:
                return None
            if re.fullmatch(r"0[xX][0-9a-fA-F]+|\d+", token):
                total += int(token, 0)
                continue
            nested = resolve(token, depth + 1)
            if nested is None:
                return None
            total += nested
        resolved[name] = total
        return total

    for name in raw:
        resolve(name)
    return resolved


def parse_rematch_trainers(battle_setup: Path) -> dict[str, tuple[str, ...]]:
    """Map each rematch table anchor trainer to its full rematch ladder."""
    text = battle_setup.read_text(encoding="utf-8")
    ladders: dict[str, tuple[str, ...]] = {}
    for body in REMATCH_PATTERN.findall(text):
        parts = [part.strip() for part in body.split(",")]
        trainers = [part for part in parts if part.startswith("TRAINER_")]
        if not trainers:
            continue
        unique: list[str] = []
        for trainer in trainers:
            if trainer not in unique and trainer != "TRAINER_NONE":
                unique.append(trainer)
        if unique:
            ladders[unique[0]] = tuple(unique)
    return ladders


def parse_script_bindings(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Return script-label -> TRAINER_* and script-label -> ITEM_* bindings."""
    trainers: dict[str, str] = {}
    items: dict[str, str] = {}
    if not path.is_file():
        return trainers, items
    labels: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        label_match = LABEL_PATTERN.match(stripped)
        if label_match:
            labels.append(label_match.group(1))
            continue
        if not stripped or stripped.startswith(("@", ".")):
            continue
        trainer_match = TRAINER_BATTLE_PATTERN.search(stripped)
        if trainer_match:
            # The bare `trainerbattle` macro leads with a TRAINER_BATTLE_* type
            # constant, so take the first token that names an actual opponent.
            opponent = next(
                (
                    token
                    for token in TRAINER_TOKEN_PATTERN.findall(trainer_match.group(1))
                    if not token.startswith("TRAINER_BATTLE_")
                ),
                "",
            )
            if opponent:
                for label in labels:
                    trainers.setdefault(label, opponent)
            else:
                trainer_match = None
        item_match = FIND_ITEM_PATTERN.search(stripped)
        if item_match:
            for label in labels:
                items.setdefault(label, item_match.group(1))
        if trainer_match or item_match or stripped.startswith("end"):
            labels = []
    return trainers, items


def display_name(constant: str, prefix: str) -> str:
    body = constant.removeprefix(prefix).replace("_", " ").title()
    return body or constant


def _marker_from_row(row: list) -> MapMarker:
    x, y, kind, glyph, title, detail, flag, *rest = row
    flags = tuple(rest[0]) if rest and rest[0] else ()
    return MapMarker(x, y, kind, glyph, title, detail, flag, flags)


def _script_title(script: str) -> str:
    _, _, tail = script.rpartition("EventScript_")
    if not tail:
        return ""
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", tail).strip()
    return spaced.removeprefix("Item ").strip() or spaced

ITEM_BALL_GRAPHICS = "OBJ_EVENT_GFX_ITEM_BALL"
BERRY_TREE_GRAPHICS = "OBJ_EVENT_GFX_BERRY_TREE"

KIND_TRAINER = "trainers"
KIND_REMATCH = "rematches"
KIND_ITEM = "items"
KIND_HIDDEN = "hidden_items"
KIND_BERRY = "berries"
KIND_FEEBAS = "feebas"
KIND_BUILDING = "buildings"

MAP_KINDS = (
    KIND_TRAINER,
    KIND_REMATCH,
    KIND_ITEM,
    KIND_HIDDEN,
    KIND_BERRY,
    KIND_BUILDING,
    KIND_FEEBAS,
)


class EmeraldMapCatalog:
    """Static map/marker data extracted from the pokeemerald decompilation."""

    def __init__(
        self,
        decomp_root: Path,
        *,
        entries: tuple[EmeraldMapEntry, ...] | None = None,
        layouts: dict[str, LayoutSpec] | None = None,
        parents: dict[str, str] | None = None,
    ) -> None:
        self._root = decomp_root
        if entries is not None and layouts is not None:
            self._layouts = layouts
            self._entries = entries
            self._by_position = {
                (entry.group, entry.number): entry for entry in self._entries
            }
            self._section_parents = dict(parents or {})
            return
        constants = decomp_root / "include" / "constants"
        self._flags = parse_defines(constants / "flags.h")
        self._trainer_ids = parse_defines(constants / "opponents.h")
        self._ladders = parse_rematch_trainers(decomp_root / "src" / "battle_setup.c")
        self._script_trainers, self._script_items = self._load_script_index()
        self._trade_maps, self._gift_items = self._load_script_extras()
        self._layouts = self._load_layouts()
        self._entries = self._load_maps()
        self._by_position = {
            (entry.group, entry.number): entry for entry in self._entries
        }
        self._section_parents = self._resolve_section_parents()

    @property
    def entries(self) -> tuple[EmeraldMapEntry, ...]:
        return self._entries

    def to_document(self, source_revision: str) -> dict:
        """Flatten the catalog so the runtime never has to parse the decomp."""
        return {
            "schema_version": MAP_SCHEMA_VERSION,
            "source_revision": source_revision,
            "parents": self._section_parents,
            "layouts": {
                spec.layout_id: [
                    spec.width,
                    spec.height,
                    spec.primary,
                    spec.secondary,
                    spec.blockdata,
                ]
                for spec in self._layouts.values()
            },
            "maps": [
                [
                    entry.map_id,
                    entry.name,
                    entry.group,
                    entry.number,
                    entry.layout_id,
                    entry.map_type,
                    entry.region_section,
                    [
                        [
                            marker.x,
                            marker.y,
                            marker.kind,
                            marker.marker,
                            marker.title,
                            marker.detail,
                            marker.flag,
                            list(marker.flags),
                        ]
                        for marker in entry.markers
                    ],
                ]
                for entry in self._entries
            ],
        }

    @classmethod
    def from_document(
        cls, decomp_root: Path, document: dict, source_revision: str
    ) -> "EmeraldMapCatalog":
        if document.get("schema_version") != MAP_SCHEMA_VERSION:
            raise ValueError("Emerald map data schema does not match this plugin")
        if document.get("source_revision") != source_revision:
            raise ValueError(
                "Emerald map data was generated from a different decomp revision"
            )
        raw_layouts = document.get("layouts")
        raw_maps = document.get("maps")
        if not isinstance(raw_layouts, dict) or not isinstance(raw_maps, list):
            raise ValueError("Emerald map data is missing layouts or maps")
        layouts = {
            layout_id: LayoutSpec(layout_id, *values)
            for layout_id, values in raw_layouts.items()
        }
        entries = tuple(
            EmeraldMapEntry(
                map_id,
                name,
                group,
                number,
                layout_id,
                tuple(_marker_from_row(marker) for marker in markers),
                map_type,
                region_section,
            )
            for map_id, name, group, number, layout_id, map_type, region_section, markers
            in raw_maps
        )
        raw_parents = document.get("parents")
        parents = raw_parents if isinstance(raw_parents, dict) else {}
        return cls(
            decomp_root, entries=entries, layouts=layouts, parents=parents
        )

    def entry(self, group: int, number: int) -> EmeraldMapEntry | None:
        return self._by_position.get((group, number))

    def layout(self, layout_id: str) -> LayoutSpec | None:
        return self._layouts.get(layout_id)

    @property
    def section_parents(self) -> dict[str, str]:
        return self._section_parents

    def _resolve_section_parents(self) -> dict[str, str]:
        """Dungeons and interiors are not drawn on the region map, so their
        contents belong to whichever mapped section you walk in from."""
        try:
            from .worldmap import parse_region_layout

            on_map = {
                section
                for row in parse_region_layout(self._root)
                for section in row
                if section != "MAPSEC_NONE"
            }
        except (OSError, ValueError, ImportError):
            return {}
        sections = {
            entry.map_id: entry.region_section
            for entry in self._entries
            if entry.region_section
        }
        warps = getattr(self, "_warps", {})
        parents: dict[str, str] = {}
        for entry in self._entries:
            section = entry.region_section
            if not section or section in on_map or section in parents:
                continue
            seen = {entry.map_id}
            queue = [entry.map_id]
            while queue:
                current = queue.pop(0)
                for _, _, destination in warps.get(current, ()):
                    if destination in seen:
                        continue
                    seen.add(destination)
                    candidate = sections.get(destination, "")
                    if candidate in on_map:
                        parents[section] = candidate
                        queue = []
                        break
                    queue.append(destination)
        return parents

    def _load_script_extras(
        self,
    ) -> tuple[frozenset[str], dict[str, tuple[tuple[str, str], ...]]]:
        """Indoor rewards are handed out by scripts, not item balls.

        Each `giveitem` is followed by the `setflag` that records it, so a gift
        can be tracked exactly like an item ball.
        """
        trades = set()
        gifts: dict[str, tuple[tuple[str, str], ...]] = {}
        for source in (self._root / "data" / "maps").glob("*/scripts.inc"):
            try:
                body = source.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if TRADE_PATTERN.search(body):
                trades.add(source.parent.name)
            found: list[tuple[str, str]] = []
            pending: str | None = None
            for line in body.splitlines():
                item = GIVE_ITEM_PATTERN.search(line)
                if item:
                    pending = item.group(1)
                    continue
                flag = SET_FLAG_PATTERN.search(line)
                if flag and pending is not None:
                    pair = (pending, flag.group(1))
                    if pair not in found:
                        found.append(pair)
                    pending = None
                elif line.strip() == "end":
                    pending = None
            if found:
                gifts[source.parent.name] = tuple(found)
        return frozenset(trades), gifts

    def _load_script_index(self) -> tuple[dict[str, str], dict[str, str]]:
        # Script labels are globally unique, and maps freely reference labels
        # defined in a sibling map's file (gym floors especially), so index the
        # whole decomp rather than one map at a time.
        trainers: dict[str, str] = {}
        items: dict[str, str] = {}
        sources = list((self._root / "data" / "scripts").glob("*.inc"))
        sources.extend((self._root / "data" / "maps").glob("*/scripts.inc"))
        for source in sources:
            found_trainers, found_items = parse_script_bindings(source)
            for label, value in found_trainers.items():
                trainers.setdefault(label, value)
            for label, value in found_items.items():
                items.setdefault(label, value)
        return trainers, items

    def _load_layouts(self) -> dict[str, LayoutSpec]:
        path = self._root / "data" / "layouts" / "layouts.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        layouts = {}
        for raw in document.get("layouts", ()):
            if not isinstance(raw, dict) or "id" not in raw:
                continue
            blockdata = raw.get("blockdata_filepath", "")
            if not blockdata:
                continue
            layouts[raw["id"]] = LayoutSpec(
                raw["id"],
                int(raw.get("width", 0)),
                int(raw.get("height", 0)),
                raw.get("primary_tileset", ""),
                raw.get("secondary_tileset", ""),
                blockdata,
            )
        return layouts

    def _load_maps(self) -> tuple[EmeraldMapEntry, ...]:
        groups_path = self._root / "data" / "maps" / "map_groups.json"
        document = json.loads(groups_path.read_text(encoding="utf-8"))
        entries = []
        self._warps: dict[str, tuple[tuple[int, int, str], ...]] = {}
        self._interiors: dict[str, EmeraldMapEntry] = {}
        for group_index, group_label in enumerate(document.get("group_order", ())):
            for map_index, map_name in enumerate(document.get(group_label, ())):
                entry = self._load_map(map_name, group_index, map_index)
                if entry is not None:
                    entries.append(entry)
                    self._interiors[entry.map_id] = entry
        return tuple(self._with_building_markers(entries))

    def _with_building_markers(
        self, entries: list[EmeraldMapEntry]
    ) -> list[EmeraldMapEntry]:
        rolled = []
        for entry in entries:
            if entry.map_type not in {"MAP_TYPE_TOWN", "MAP_TYPE_CITY"}:
                rolled.append(entry)
                continue
            extra = []
            for x, y, destination in self._warps.get(entry.map_id, ()):
                interior = self._interiors.get(destination)
                if interior is None or interior.map_type in OUTDOOR_MAP_TYPES:
                    continue
                summary = self._interior_summary(interior)
                if not summary:
                    continue
                extra.append(
                    MapMarker(
                        x,
                        y,
                        KIND_BUILDING,
                        "building",
                        display_name(interior.map_id, "MAP_"),
                        "\n".join(summary),
                        None,
                        self._interior_flags(interior),
                    )
                )
            rolled.append(
                replace(entry, markers=entry.markers + tuple(extra))
                if extra
                else entry
            )
        return rolled

    def _interior_flags(self, interior: EmeraldMapEntry) -> tuple[int, ...]:
        """Every flag that has to be set before this building is exhausted."""
        flags = [
            marker.flag
            for marker in interior.markers
            if marker.kind in {KIND_ITEM, KIND_HIDDEN} and marker.flag is not None
        ]
        for _, flag_name in self._gift_items.get(interior.name, ()):
            resolved = self._flags.get(flag_name)
            if resolved is not None:
                flags.append(resolved)
        return tuple(dict.fromkeys(flags))

    def _interior_summary(self, interior: EmeraldMapEntry) -> list[str]:
        """What is worth walking into this building for."""
        lines = []
        for kind, label in (
            (KIND_ITEM, "item"),
            (KIND_HIDDEN, "hidden item"),
        ):
            found = [marker for marker in interior.markers if marker.kind == kind]
            if found:
                names = ", ".join(sorted({marker.title for marker in found}))
                lines.append(
                    f"{len(found)} {label}{'s' if len(found) != 1 else ''}: {names}"
                )
        gifts = self._gift_items.get(interior.name, ())
        if gifts:
            names = ", ".join(display_name(item, "ITEM_") for item, _ in gifts)
            lines.append(f"Gift: {names}")
        if interior.name in self._trade_maps:
            lines.append("In-game trade available")
        return lines

    def _load_map(
        self, map_name: str, group: int, number: int
    ) -> EmeraldMapEntry | None:
        directory = self._root / "data" / "maps" / map_name
        map_path = directory / "map.json"
        if not map_path.is_file():
            return None
        try:
            document = json.loads(map_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        layout_id = document.get("layout", "")
        if layout_id not in self._layouts:
            return None
        markers = self._map_markers(document, self._script_trainers, self._script_items)
        map_id = document.get("id", f"MAP_{map_name.upper()}")
        warps = tuple(
            (int(warp.get("x", 0)), int(warp.get("y", 0)), str(warp.get("dest_map", "")))
            for warp in document.get("warp_events", ())
            if isinstance(warp, dict) and warp.get("dest_map")
        )
        if warps:
            self._warps[map_id] = warps
        return EmeraldMapEntry(
            map_id,
            map_name,
            group,
            number,
            layout_id,
            markers,
            str(document.get("map_type", "")),
            str(document.get("region_map_section", "")),
        )

    def _map_markers(
        self,
        document: dict,
        trainers: dict[str, str],
        items: dict[str, str],
    ) -> tuple[MapMarker, ...]:
        markers: list[MapMarker] = []
        for event in document.get("object_events", ()):
            if not isinstance(event, dict):
                continue
            marker = self._object_marker(event, trainers, items)
            if marker is not None:
                markers.append(marker)
        for event in document.get("bg_events", ()):
            if not isinstance(event, dict) or event.get("type") != "hidden_item":
                continue
            item = event.get("item", "")
            markers.append(
                MapMarker(
                    int(event.get("x", 0)),
                    int(event.get("y", 0)),
                    KIND_HIDDEN,
                    "quest",
                    display_name(item, "ITEM_") or "Hidden item",
                    "Hidden item (needs Itemfinder)"
                    + (" · underfoot" if event.get("underfoot") else ""),
                    self._flags.get(str(event.get("flag", ""))),
                )
            )
        return tuple(markers)

    def _object_marker(
        self,
        event: dict,
        trainers: dict[str, str],
        items: dict[str, str],
    ) -> MapMarker | None:
        x = int(event.get("x", 0))
        y = int(event.get("y", 0))
        script = str(event.get("script", ""))
        graphics = str(event.get("graphics_id", ""))
        if str(event.get("trainer_type", "TRAINER_TYPE_NONE")) != "TRAINER_TYPE_NONE":
            constant = trainers.get(script, "")
            trainer_id = self._trainer_ids.get(constant)
            ladder = self._ladders.get(constant, ())
            name = display_name(constant, "TRAINER_") if constant else "Trainer"
            if ladder:
                detail = "Rebattlable · ladder: " + " -> ".join(
                    display_name(step, "TRAINER_") for step in ladder
                )
                kind, glyph = KIND_REMATCH, "boss"
            else:
                detail = "Single battle only"
                kind, glyph = KIND_TRAINER, "person"
            flag = (
                TRAINER_FLAGS_START + trainer_id if trainer_id is not None else None
            )
            return MapMarker(x, y, kind, glyph, name, detail, flag)
        if graphics == ITEM_BALL_GRAPHICS:
            item = items.get(script, "")
            flag = self._flags.get(str(event.get("flag", "")))
            if item:
                title = display_name(item, "ITEM_")
                detail = "Visible item ball"
            else:
                # Scripted pickups (starters, gift Pokemon, Electrode battles)
                # use an item-ball sprite without a finditem, and the Battle
                # Pyramid rolls its contents per run.
                title = _script_title(script) or "Item ball"
                detail = (
                    "Contents vary per run"
                    if flag is None
                    else "Scripted pickup"
                )
            return MapMarker(x, y, KIND_ITEM, "item", title, detail, flag)
        if graphics == BERRY_TREE_GRAPHICS:
            tree = str(event.get("trainer_sight_or_berry_tree_id", ""))
            return MapMarker(
                x,
                y,
                KIND_BERRY,
                "service",
                "Berry tree",
                display_name(tree, "BERRY_TREE_") if tree else "",
                None,
            )
        return None


TILESET_PREFIX = "gTileset_"


def tileset_directory(root: Path, label: str) -> Path:
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", label.removeprefix(TILESET_PREFIX)).lower()
    for kind in ("primary", "secondary"):
        candidate = root / "data" / "tilesets" / kind / name
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"Unknown Emerald tileset: {label}")


class EmeraldMapImages:
    """Lazily renders decompiled layouts to cached PNGs for the map window."""

    def __init__(
        self,
        catalog: EmeraldMapCatalog,
        decomp_root: Path,
        cache_directory: Path,
        load_tileset,
        render_layout,
    ) -> None:
        self._catalog = catalog
        self._root = decomp_root
        self._cache = cache_directory
        self._load_tileset = load_tileset
        self._render_layout = render_layout
        self._tilesets: dict[str, object] = {}

    def _tileset(self, label: str):
        if label not in self._tilesets:
            self._tilesets[label] = self._load_tileset(
                tileset_directory(self._root, label)
            )
        return self._tilesets[label]

    def image_path(self, layout_id: str) -> Path:
        name = layout_id.removeprefix("LAYOUT_").lower()
        return self._cache / "maps" / f"{name}.png"

    def render(self, layout_id: str) -> Path:
        spec = self._catalog.layout(layout_id)
        if spec is None:
            raise ValueError(f"Unknown Emerald layout: {layout_id}")
        output = self.image_path(layout_id)
        if output.is_file():
            return output
        blocks = (self._root / spec.blockdata).read_bytes()
        return self._render_layout(
            blocks,
            spec.width,
            spec.height,
            self._tileset(spec.primary),
            self._tileset(spec.secondary),
            output,
        )

    def layers(self) -> tuple:
        from retroarch_overlay.models import MapLayer

        layers = []
        for entry in self._catalog.entries:
            spec = self._catalog.layout(entry.layout_id)
            if spec is None:
                continue
            layers.append(
                MapLayer(
                    entry.key,
                    display_name(entry.map_id, "MAP_"),
                    "Hoenn",
                    self.image_path(entry.layout_id),
                    credit="Rendered locally from the pokeemerald decompilation",
                    wrap_width=spec.width,
                    wrap_height=spec.height,
                    anchor_x=8,
                    anchor_y=8,
                    map_id=entry.numeric_id,
                    image_loader=(
                        lambda layout_id=entry.layout_id: self.render(layout_id)
                    ),
                )
            )
        return tuple(layers)
