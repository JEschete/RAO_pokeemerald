import json
import ast
import re
from pathlib import Path
from typing import Any

from .feebas import load_route119_fishing_spots


SCHEMA_VERSION = 2
SOURCE_REVISION = "5eff78649e7170a877b961ef0b3da13b81a16038"


def build_knowledge(root: Path) -> dict[str, Any]:
    constants = root / "include" / "constants"
    species_ids = parse_numeric_defines(constants / "species.h")
    flag_ids = parse_numeric_defines(constants / "flags.h")
    trainer_ids = parse_numeric_defines(constants / "opponents.h")
    variable_ids = parse_numeric_defines(constants / "vars.h")
    type_ids = parse_numeric_defines(constants / "pokemon.h")
    ability_ids = parse_numeric_defines(constants / "abilities.h")
    move_ids = parse_numeric_defines(constants / "moves.h")
    item_ids = parse_enum(constants / "items.h", "ITEM_")
    national_dex = load_national_dex_numbers(constants / "pokedex.h")
    with (root / "src" / "data" / "wild_encounters.json").open(encoding="utf-8") as file:
        encounter_group = json.load(file)["wild_encounter_groups"][0]
    with (root / "data" / "maps" / "map_groups.json").open(encoding="utf-8") as file:
        map_groups = json.load(file)
    species = load_species_info(
        root / "src" / "data" / "pokemon" / "species_info.h",
        type_ids,
        ability_ids,
        item_ids,
    )
    moves = load_move_info(root / "src" / "data" / "battle_moves.h", move_ids, type_ids)
    type_chart = load_type_chart(root / "src" / "battle_main.c", type_ids)
    items = load_item_names(root / "src" / "data" / "items.h", item_ids)
    map_names = tuple(
        map_name
        for group_name in map_groups["group_order"]
        for map_name in map_groups[group_name]
    )
    route_trackers = build_route_trackers(root, map_names, flag_ids, trainer_ids)
    item_locations = load_item_locations(root, map_names, flag_ids)
    rematches = load_rematches(root / "src" / "battle_setup.c")
    fishing_spots = load_route119_fishing_spots(root)
    trainers = load_trainers(
        root / "src" / "data" / "trainers.h",
        root / "src" / "data" / "trainer_parties.h",
        trainer_ids,
    )
    evolutions = load_evolutions(
        root / "src" / "data" / "pokemon" / "evolution.h"
    )
    static_acquisitions = load_static_acquisitions(root, map_names)
    map_connections = load_map_connections(root, map_names)
    frontier_mons = load_frontier_mons(root, move_ids, item_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_revision": SOURCE_REVISION,
        "encounter_group": encounter_group,
        "map_groups": map_groups,
        "national_dex": national_dex,
        "species_ids": species_ids,
        "flag_ids": flag_ids,
        "trainer_ids": trainer_ids,
        "variable_ids": variable_ids,
        "types": invert_constants(type_ids, "TYPE_"),
        "abilities": invert_constants(ability_ids, "ABILITY_"),
        "items": items,
        "moves": moves,
        "type_chart": type_chart,
        "species": species,
        "route_trackers": route_trackers,
        "item_locations": item_locations,
        "rematches": rematches,
        "route119_fishing_spots": {
            f"{x},{y}": spot for (x, y), spot in fishing_spots.items()
        },
        "trainers": trainers,
        "evolutions": evolutions,
        "static_acquisitions": static_acquisitions,
        "map_connections": map_connections,
        "frontier_mons": frontier_mons,
    }


def parse_numeric_defines(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    pending: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"#define\s+(\w+)\s+(.+?)(?:\s*//.*)?$", line)
        if not match:
            continue
        name, expression = match.groups()
        expression = _strip_outer_parentheses(expression.strip())
        pending[name] = expression
        comment_value = re.search(r"//\s*(0x[0-9A-Fa-f]+|\d+)\b", line)
        if comment_value:
            values[name] = int(comment_value.group(1), 0)
    changed = True
    while changed:
        changed = False
        for name, expression in tuple(pending.items()):
            try:
                value = _integer_expression(expression, values)
            except (SyntaxError, ValueError, KeyError):
                continue
            if values.get(name) != value:
                values[name] = value
                changed = True
    return values


def _strip_outer_parentheses(expression: str) -> str:
    while expression.startswith("(") and expression.endswith(")"):
        depth = 0
        closes_at_end = True
        for index, character in enumerate(expression):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0 and index != len(expression) - 1:
                    closes_at_end = False
                    break
        if not closes_at_end or depth != 0:
            break
        expression = expression[1:-1].strip()
    return expression


def _integer_expression(expression: str, values: dict[str, int]) -> int:
    node = ast.parse(expression, mode="eval").body

    def resolve(current: ast.expr) -> int:
        if isinstance(current, ast.Constant) and isinstance(current.value, int):
            return current.value
        if isinstance(current, ast.Name):
            return values[current.id]
        if isinstance(
            current,
            ast.BinOp,
        ) and isinstance(current.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod)):
            left = resolve(current.left)
            right = resolve(current.right)
            if isinstance(current.op, ast.Add):
                return left + right
            if isinstance(current.op, ast.Sub):
                return left - right
            if isinstance(current.op, ast.Mult):
                return left * right
            if isinstance(current.op, ast.FloorDiv):
                return left // right
            return left % right
        raise ValueError("unsupported integer expression")

    return resolve(node)


def parse_enum(path: Path, prefix: str) -> dict[str, int]:
    values: dict[str, int] = {}
    in_enum = False
    current = -1
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("//", 1)[0].strip().rstrip(",")
        if line.startswith("enum") and "{" in line:
            in_enum = True
            continue
        if not in_enum:
            continue
        if line.startswith("}"):
            break
        match = re.fullmatch(r"([A-Z0-9_]+)(?:\s*=\s*(.+))?", line)
        if not match or not match.group(1).startswith(prefix):
            continue
        name, expression = match.groups()
        if expression is None:
            current += 1
        elif re.fullmatch(r"0x[0-9A-Fa-f]+|\d+", expression.strip()):
            current = int(expression.strip(), 0)
        elif expression.strip() in values:
            current = values[expression.strip()]
        else:
            continue
        values[name] = current
    return values


def load_national_dex_numbers(path: Path) -> dict[str, int]:
    numbers: dict[str, int] = {}
    in_order = False
    value = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip().rstrip(",")
        if stripped == "enum {" and not in_order:
            in_order = True
            continue
        if not in_order:
            continue
        if stripped == "};":
            break
        if stripped.startswith("NATIONAL_DEX_"):
            numbers[stripped.replace("NATIONAL_DEX_", "SPECIES_", 1)] = value
            value += 1
    return numbers


def load_species_info(
    path: Path,
    type_ids: dict[str, int],
    ability_ids: dict[str, int],
    item_ids: dict[str, int],
) -> dict[str, dict[str, Any]]:
    entries = split_entries(path.read_text(encoding="utf-8"), "SPECIES_")
    species: dict[str, dict[str, Any]] = {}
    for name, entry in entries.items():
        types = constant_list(entry, "types", "TYPE_")
        abilities = constant_list(entry, "abilities", "ABILITY_")
        egg_groups = constant_list(entry, "eggGroups", "EGG_GROUP_")
        if len(types) != 2 or len(abilities) != 2:
            continue
        species[name] = {
            "types": [type_ids.get(value, -1) for value in types],
            "catch_rate": numeric_field(entry, "catchRate"),
            "exp_yield": numeric_field(entry, "expYield"),
            "ev_yield": [
                numeric_field(entry, field)
                for field in (
                    "evYield_HP",
                    "evYield_Attack",
                    "evYield_Defense",
                    "evYield_Speed",
                    "evYield_SpAttack",
                    "evYield_SpDefense",
                )
            ],
            "items": [
                item_ids.get(constant_field(entry, "itemCommon", "ITEM_") or "", 0),
                item_ids.get(constant_field(entry, "itemRare", "ITEM_") or "", 0),
            ],
            "egg_cycles": numeric_field(entry, "eggCycles"),
            "egg_groups": egg_groups,
            "abilities": [ability_ids.get(value, 0) for value in abilities],
            "gender_ratio": gender_ratio(entry),
            "growth_rate": constant_field(entry, "growthRate", "GROWTH_") or "",
        }
    return species


def load_move_info(
    path: Path, move_ids: dict[str, int], type_ids: dict[str, int]
) -> dict[str, dict[str, Any]]:
    entries = split_entries(path.read_text(encoding="utf-8"), "MOVE_")
    result = {}
    for name, entry in entries.items():
        if name not in move_ids:
            continue
        result[str(move_ids[name])] = {
            "key": name,
            "name": display_constant(name, "MOVE_"),
            "power": numeric_field(entry, "power"),
            "accuracy": numeric_field(entry, "accuracy"),
            "pp": numeric_field(entry, "pp"),
            "type": type_ids.get(constant_field(entry, "type", "TYPE_") or "", -1),
        }
    return result


def load_type_chart(path: Path, type_ids: dict[str, int]) -> list[list[int]]:
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"const u8 gTypeEffectiveness\[\d+\]\s*=\s*\{(.*?)TYPE_ENDTABLE",
        text,
        re.DOTALL,
    )
    if match is None:
        raise ValueError("Could not find gTypeEffectiveness in battle_main.c")
    multipliers = {
        "TYPE_MUL_NO_EFFECT": 0,
        "TYPE_MUL_NOT_EFFECTIVE": 5,
        "TYPE_MUL_NORMAL": 10,
        "TYPE_MUL_SUPER_EFFECTIVE": 20,
    }
    rows = []
    for attack, defense, multiplier in re.findall(
        r"(TYPE_[A-Z_]+)\s*,\s*(TYPE_[A-Z_]+)\s*,\s*(TYPE_MUL_[A-Z_]+)",
        match.group(1),
    ):
        if attack not in type_ids or defense not in type_ids or multiplier not in multipliers:
            continue
        rows.append([type_ids[attack], type_ids[defense], multipliers[multiplier]])
    return rows


def load_item_names(path: Path, item_ids: dict[str, int]) -> dict[str, str]:
    entries = split_entries(path.read_text(encoding="utf-8"), "ITEM_")
    result = {}
    for key, value in item_ids.items():
        entry = entries.get(key, "")
        match = re.search(r"\.name\s*=\s*_\(\"([^\"]*)\"\)", entry)
        result[str(value)] = (
            match.group(1).title() if match else display_constant(key, "ITEM_")
        )
    return result


def load_trainers(
    trainers_path: Path,
    parties_path: Path,
    trainer_ids: dict[str, int],
) -> dict[str, dict[str, Any]]:
    party_text = parties_path.read_text(encoding="utf-8")
    parties = {}
    party_pattern = re.compile(
        r"static const struct \w+ (sParty_\w+)\[\]\s*=\s*\{(.*?)^\};",
        re.MULTILINE | re.DOTALL,
    )
    for party_match in party_pattern.finditer(party_text):
        rows = []
        for mon in re.split(r"(?=^    \{\s*$)", party_match.group(2), flags=re.MULTILINE):
            species = re.search(r"\.species\s*=\s*(SPECIES_[A-Z0-9_]+)", mon)
            level = re.search(r"\.lvl\s*=\s*(\d+)", mon)
            if species and level:
                rows.append({"species": species.group(1), "level": int(level.group(1))})
        parties[party_match.group(1)] = rows
    trainers = {}
    for key, entry in split_entries(
        trainers_path.read_text(encoding="utf-8"), "TRAINER_"
    ).items():
        trainer_id = trainer_ids.get(key)
        party = re.search(r"\b(sParty_\w+)\b", entry)
        name = re.search(r"\.trainerName\s*=\s*_\(\"([^\"]*)\"\)", entry)
        if trainer_id is None or party is None:
            continue
        trainers[str(trainer_id)] = {
            "key": key,
            "name": name.group(1).title() if name else display_constant(key, "TRAINER_"),
            "double": bool(re.search(r"\.doubleBattle\s*=\s*TRUE", entry)),
            "party": parties.get(party.group(1), []),
        }
    return trainers


def load_evolutions(path: Path) -> dict[str, list[dict[str, str]]]:
    result = {}
    for species, entry in split_entries(
        path.read_text(encoding="utf-8"), "SPECIES_"
    ).items():
        rows = []
        for method, parameter, target in re.findall(
            r"\{(EVO_[A-Z0-9_]+)\s*,\s*([^,}]+)\s*,\s*(SPECIES_[A-Z0-9_]+)\}",
            entry,
        ):
            rows.append(
                {
                    "method": method,
                    "parameter": parameter.strip(),
                    "target": target,
                }
            )
        if rows:
            result[species] = rows
    return result


def load_frontier_mons(
    root: Path,
    move_ids: dict[str, int],
    item_ids: dict[str, int],
) -> list[dict[str, Any]]:
    """gBattleFrontierMons indexed by monId, as stored in RentalMon records."""
    constants = root / "include" / "constants"
    frontier_ids = parse_numeric_defines(constants / "battle_frontier_mons.h")
    table_ids = parse_numeric_defines(constants / "battle_frontier.h")
    nature_ids = parse_numeric_defines(constants / "pokemon.h")
    held_items = {}
    for table_name, item_name in re.findall(
        r"\[(BATTLE_FRONTIER_ITEM_\w+)\]\s*=\s*(ITEM_\w+)",
        (root / "src" / "battle_tower.c").read_text(encoding="utf-8"),
    ):
        table_id = table_ids.get(table_name)
        if table_id is not None:
            held_items[table_id] = item_ids.get(item_name, 0)
    entries = split_entries(
        (
            root / "src" / "data" / "battle_frontier" / "battle_frontier_mons.h"
        ).read_text(encoding="utf-8"),
        "FRONTIER_MON_",
    )
    count = 1 + max(
        (frontier_ids.get(name, -1) for name in entries), default=-1
    )
    result: list[dict[str, Any]] = [{} for _ in range(count)]
    for name, entry in entries.items():
        index = frontier_ids.get(name)
        if index is None:
            continue
        species = constant_field(entry, "species", "SPECIES_")
        table_name = constant_field(entry, "itemTableId", "BATTLE_FRONTIER_ITEM_")
        table_id = table_ids.get(table_name) if table_name else None
        nature = constant_field(entry, "nature", "NATURE_")
        result[index] = {
            "species": species or "",
            "moves": [
                move_ids.get(move, 0)
                for move in constant_list(entry, "moves", "MOVE_")
            ],
            "item": held_items.get(table_id or 0, 0),
            "nature": nature_ids.get(nature or "", 0),
        }
    return result


def load_static_acquisitions(
    root: Path, map_names: tuple[str, ...]
) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    maps_root = root / "data" / "maps"
    patterns = (
        ("gift", r"\bgivemon\s+(SPECIES_[A-Z0-9_]+)"),
        ("egg", r"\bgiveegg\s+(SPECIES_[A-Z0-9_]+)"),
        ("static", r"\bsetwildbattle\s+(SPECIES_[A-Z0-9_]+)"),
    )
    for map_name in map_names:
        path = maps_root / map_name / "scripts.inc"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for kind, pattern in patterns:
            for species in sorted(set(re.findall(pattern, text))):
                result.setdefault(species, []).append(
                    {"kind": kind, "map": map_name}
                )
    return result


def load_map_connections(
    root: Path, map_names: tuple[str, ...]
) -> dict[str, list[str]]:
    maps_root = root / "data" / "maps"
    id_to_name = {}
    documents = {}
    for map_name in map_names:
        path = maps_root / map_name / "map.json"
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        documents[map_name] = document
        map_id = document.get("id")
        if isinstance(map_id, str):
            id_to_name[map_id] = map_name
    graph: dict[str, set[str]] = {name: set() for name in documents}
    for map_name, document in documents.items():
        targets = [
            value.get("map") for value in (document.get("connections") or ())
        ] + [
            value.get("dest_map") for value in (document.get("warp_events") or ())
        ]
        for target_id in targets:
            target = id_to_name.get(target_id)
            if target is None or target == map_name:
                continue
            graph[map_name].add(target)
            graph.setdefault(target, set()).add(map_name)
    return {name: sorted(values) for name, values in sorted(graph.items())}


def build_route_trackers(
    root: Path,
    map_names: tuple[str, ...],
    flag_ids: dict[str, int],
    trainer_ids: dict[str, int],
) -> dict[str, dict[str, Any]]:
    result = {}
    maps_root = root / "data" / "maps"
    for map_name in map_names:
        script_path = maps_root / map_name / "scripts.inc"
        if not script_path.is_file():
            continue
        script = script_path.read_text(encoding="utf-8")
        trainer_groups: dict[str, list[int]] = {}
        for trainer_name in sorted(set(re.findall(r"\bTRAINER_[A-Z0-9_]+", script))):
            trainer_id = trainer_ids.get(trainer_name)
            if trainer_id is None:
                continue
            group = re.sub(r"^TRAINER_(?:MAY|BRENDAN)_", "TRAINER_RIVAL_", trainer_name)
            group = re.sub(r"_(?:[1-6]|TREECKO|TORCHIC|MUDKIP)$", "", group)
            trainer_groups.setdefault(group, []).append(trainer_id)
        for trainer_group in trainer_groups.values():
            trainer_group.sort()
        map_location_key = location_key(map_name)
        referenced_flags = set(re.findall(r"\bFLAG_[A-Z0-9_]+", script))
        item_flags = {
            objective_label(name, map_location_key): flag_id
            for name, flag_id in flag_ids.items()
            if name.startswith(("FLAG_ITEM_", "FLAG_HIDDEN_ITEM_"))
            and map_location_key in name
        }
        objective_flags = {
            objective_label(name, map_location_key): flag_ids[name]
            for name in sorted(referenced_flags)
            if name in flag_ids
            and name.startswith(
                (
                    "FLAG_DEFEATED_", "FLAG_RECEIVED_", "FLAG_DELIVERED_",
                    "FLAG_RETURNED_", "FLAG_RECOVERED_", "FLAG_MET_",
                )
            )
        }
        result[map_name] = {
            "trainer_groups": trainer_groups,
            "item_flags": item_flags,
            "objective_flags": objective_flags,
        }
    return result


def load_item_locations(
    root: Path, map_names: tuple[str, ...], flag_ids: dict[str, int]
) -> dict[str, list[list[Any]]]:
    result = {}
    maps_root = root / "data" / "maps"
    for map_name in map_names:
        path = maps_root / map_name / "map.json"
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        rows = []
        for event in document.get("object_events", ()):
            flag_name = event.get("flag", "")
            if event.get("graphics_id") != "OBJ_EVENT_GFX_ITEM_BALL":
                continue
            flag_id = flag_ids.get(flag_name)
            if flag_id is not None:
                rows.append([
                    objective_label(flag_name, location_key(map_name)),
                    event["x"], event["y"], flag_id, False,
                ])
        for event in document.get("bg_events", ()):
            if event.get("type") != "hidden_item":
                continue
            flag_id = flag_ids.get(event.get("flag", ""))
            if flag_id is not None:
                rows.append([
                    display_constant(event["item"], "ITEM_"),
                    event["x"], event["y"], flag_id, True,
                ])
        if rows:
            result[map_name] = rows
    return result


def load_rematches(path: Path) -> dict[str, list[list[Any]]]:
    result: dict[str, list[list[Any]]] = {}
    pattern = re.compile(
        r"^\s*\[REMATCH_([A-Z0-9_]+)\]\s*=\s*REMATCH\([^\n]+,\s*MAP_([A-Z0-9_]+)\),",
        re.MULTILINE,
    )
    for index, match in enumerate(pattern.finditer(path.read_text(encoding="utf-8"))):
        trainer, map_name = match.groups()
        normalized = re.sub(r"[^A-Z0-9]", "", map_name.upper())
        result.setdefault(normalized, []).append([index, display_constant(trainer, "")])
    return result


def split_entries(text: str, prefix: str) -> dict[str, str]:
    pattern = re.compile(rf"^\s*\[({re.escape(prefix)}[A-Z0-9_]+)\]\s*=", re.MULTILINE)
    matches = list(pattern.finditer(text))
    return {
        match.group(1): text[match.start() : matches[index + 1].start()]
        if index + 1 < len(matches)
        else text[match.start() :]
        for index, match in enumerate(matches)
    }


def numeric_field(entry: str, field: str) -> int:
    match = re.search(rf"\.{re.escape(field)}\s*=\s*(\d+)", entry)
    return int(match.group(1)) if match else 0


def constant_field(entry: str, field: str, prefix: str) -> str | None:
    match = re.search(rf"\.{re.escape(field)}\s*=\s*({re.escape(prefix)}[A-Z0-9_]+)", entry)
    return match.group(1) if match else None


def constant_list(entry: str, field: str, prefix: str) -> list[str]:
    match = re.search(rf"\.{re.escape(field)}\s*=\s*\{{([^}}]+)\}}", entry)
    return re.findall(rf"\b{re.escape(prefix)}[A-Z0-9_]+\b", match.group(1)) if match else []


def gender_ratio(entry: str) -> int:
    match = re.search(r"\.genderRatio\s*=\s*([^,\n]+)", entry)
    if match is None:
        return 255
    value = match.group(1).strip()
    constants = {"MON_MALE": 0, "MON_FEMALE": 254, "MON_GENDERLESS": 255}
    if value in constants:
        return constants[value]
    percent = re.fullmatch(r"PERCENT_FEMALE\((\d+(?:\.\d+)?)\)", value)
    if percent:
        return min(254, int(float(percent.group(1)) * 255 / 100))
    return 255


def invert_constants(values: dict[str, int], prefix: str) -> dict[str, str]:
    return {
        str(value): display_constant(name, prefix)
        for name, value in values.items()
        if name.startswith(prefix)
    }


def display_constant(value: str, prefix: str) -> str:
    return " ".join(word.capitalize() for word in value.removeprefix(prefix).split("_"))


def location_key(map_name: str) -> str:
    return re.sub(
        r"(?<=[A-Za-z])(?=\d)",
        "_",
        re.sub(r"(?<=[a-z])(?=[A-Z])", "_", map_name),
    ).upper()


def objective_label(name: str, map_key: str) -> str:
    text = name.removeprefix("FLAG_")
    for prefix in (
        "HIDDEN_ITEM_", "ITEM_", "DEFEATED_", "RECEIVED_", "DELIVERED_",
        "RETURNED_", "RECOVERED_", "MET_",
    ):
        text = text.removeprefix(prefix)
    return display_constant(text.replace(map_key, "").strip("_"), "")