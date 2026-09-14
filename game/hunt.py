"""Wild-encounter statistics: per-species session and lifetime counters.

Battle outcomes are classified from observable state only: an opponent that
reached 0 HP was knocked out; a newly set Pokédex caught-flag or the wild
Pokémon's personality appearing in the party means it was caught; anything
else counts as fled (this includes escapes in either direction, and a catch
that went straight to a PC box for an already-registered species, which the
plugin cannot observe).
"""

import json
from pathlib import Path

from .state import BattlePokemonState, PokemonState

OUTCOMES = ("ko", "caught", "fled")


class HuntTracker:
    def __init__(self, state_directory: Path | None) -> None:
        self._state_directory = state_directory
        self.identity = ""
        self.path: Path | None = None
        self.lifetime: dict[str, dict[str, int]] = {}
        self.session: dict[str, int] = {}
        self._active: dict[str, object] | None = None

    def select_playthrough(self, trainer_id: int) -> None:
        identity = f"{trainer_id:08x}"
        if identity == self.identity:
            return
        self.identity = identity
        self.path = (
            self._state_directory / f"hunt-{identity}.json"
            if self._state_directory is not None
            else None
        )
        self.lifetime = self._load()
        self.session = {}
        self._active = None

    def reset_session(self) -> None:
        self.identity = ""
        self.path = None
        self.lifetime = {}
        self.session = {}
        self._active = None

    # --- battle lifecycle -------------------------------------------------

    def battle_started(
        self, opponent: BattlePokemonState, already_caught: bool
    ) -> None:
        active = self._active
        if (
            active is not None
            and active["species"] == opponent.species
            and active["personality"] == opponent.personality
        ):
            active["hp"] = opponent.hp
            return
        if active is not None:
            # A new wild battle began before we saw the old one end.
            self._record_outcome("fled")
        self._active = {
            "species": opponent.species,
            "personality": opponent.personality,
            "hp": opponent.hp,
            "already_caught": already_caught,
        }
        self.session[opponent.species] = self.session.get(opponent.species, 0) + 1
        entry = self._entry(opponent.species)
        entry["seen"] += 1
        self.save()

    def battle_ended(
        self,
        caught_now: bool,
        party: tuple[PokemonState, ...],
    ) -> str | None:
        active = self._active
        if active is None:
            return None
        if int(active["hp"]) <= 0:
            outcome = "ko"
        elif caught_now and not active["already_caught"]:
            outcome = "caught"
        elif any(
            member.personality == active["personality"] for member in party
        ):
            outcome = "caught"
        else:
            outcome = "fled"
        self._record_outcome(outcome)
        return outcome

    def active_species(self) -> str | None:
        return str(self._active["species"]) if self._active is not None else None

    def stats_for(self, species: str) -> dict[str, int] | None:
        entry = self.lifetime.get(species)
        return dict(entry) if entry is not None else None

    def _record_outcome(self, outcome: str) -> None:
        active = self._active
        self._active = None
        if active is None:
            return
        entry = self._entry(str(active["species"]))
        entry[outcome] = entry.get(outcome, 0) + 1
        self.save()

    def _entry(self, species: str) -> dict[str, int]:
        return self.lifetime.setdefault(
            species, {"seen": 0, "ko": 0, "caught": 0, "fled": 0}
        )

    # --- persistence ------------------------------------------------------

    def save(self) -> None:
        if self.path is None:
            return
        document = {
            "schema_version": 1,
            "playthrough": self.identity,
            "species": self.lifetime,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError:
            return

    def _load(self) -> dict[str, dict[str, int]]:
        if self.path is None or not self.path.is_file():
            return {}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if (
            document.get("schema_version") != 1
            or document.get("playthrough") != self.identity
        ):
            return {}
        entries = document.get("species", {})
        if not isinstance(entries, dict):
            return {}
        result: dict[str, dict[str, int]] = {}
        for species, value in entries.items():
            if not isinstance(species, str) or not isinstance(value, dict):
                continue
            cleaned = {
                key: int(value.get(key, 0))
                for key in ("seen", "ko", "caught", "fled")
                if isinstance(value.get(key, 0), int)
            }
            if len(cleaned) == 4 and cleaned["seen"] > 0:
                result[species] = cleaned
        return result
