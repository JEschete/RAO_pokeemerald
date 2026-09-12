import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .knowledge_builder import SCHEMA_VERSION, SOURCE_REVISION


@dataclass(frozen=True, slots=True)
class EmeraldKnowledge:
    document: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "EmeraldKnowledge":
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Emerald knowledge is unavailable: {error}") from error
        if not isinstance(document, dict):
            raise ValueError("Emerald knowledge must contain a JSON object")
        if document.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Emerald knowledge schema does not match this plugin")
        if document.get("source_revision") != SOURCE_REVISION:
            raise ValueError("Emerald knowledge was generated from a different decomp revision")
        for key in (
            "encounter_group", "map_groups", "national_dex", "species_ids",
            "flag_ids", "trainer_ids", "variable_ids", "species", "items", "moves",
            "route_trackers", "item_locations", "rematches", "trainers",
            "evolutions", "static_acquisitions",
            "map_connections",
        ):
            if not isinstance(document.get(key), dict):
                raise ValueError(f"Emerald knowledge field {key!r} must be an object")
        for key in ("type_chart", "frontier_mons"):
            if not isinstance(document.get(key), list):
                raise ValueError(f"Emerald knowledge field {key!r} must be an array")
        return cls(document)

    def __getitem__(self, key: str) -> Any:
        return self.document[key]