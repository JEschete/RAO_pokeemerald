"""A per-playthrough journal of notable events, kept on disk as JSONL and
rendered to a companion Markdown file.

Events are detected by diffing observable save state between snapshots:
new Pokédex caught-flags, badge and Frontier symbol flags, and party level
ups. The first observation of a playthrough only records a baseline.
"""

import json
import re
import time
from pathlib import Path

from retroarch_overlay.models import PanelAction, PanelRow, PanelSection

from .state import PokemonState

BADGE_FLAG_START = 0x867
BADGE_NAMES = (
    "Stone Badge", "Knuckle Badge", "Dynamo Badge", "Heat Badge",
    "Balance Badge", "Feather Badge", "Mind Badge", "Rain Badge",
)
SYMBOL_FLAG_NAMES = tuple(
    (f"FLAG_SYS_{facility.upper()}_{color.upper()}", f"{facility} {color} symbol")
    for facility in ("Tower", "Dome", "Palace", "Arena", "Factory", "Pike", "Pyramid")
    for color in ("Silver", "Gold")
)
MEMORY_EVENTS = 200


def _display_species(species: str) -> str:
    label = " ".join(
        word.capitalize() for word in species.removeprefix("SPECIES_").split("_")
    )
    return re.sub(r"(?<=\D)(?=\d)", " ", label)


class SessionJournal:
    def __init__(self, state_directory: Path | None) -> None:
        self._state_directory = state_directory
        self.identity = ""
        self.path: Path | None = None
        self.markdown_path: Path | None = None
        self.events: list[tuple[str, str, str]] = []

    def select_playthrough(self, trainer_id: int) -> None:
        identity = f"{trainer_id:08x}"
        if identity == self.identity:
            return
        self.identity = identity
        if self._state_directory is None:
            self.path = None
            self.markdown_path = None
        else:
            self.path = self._state_directory / f"journal-{identity}.jsonl"
            self.markdown_path = self._state_directory / f"journal-{identity}.md"
        self.events = self._load_recent()

    def reset_session(self) -> None:
        self.identity = ""
        self.path = None
        self.markdown_path = None
        self.events = []

    def record(self, kind: str, text: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        self.events.append((timestamp, kind, text))
        del self.events[:-MEMORY_EVENTS]
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {"at": timestamp, "kind": kind, "text": text},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            if self.markdown_path is not None:
                new_file = not self.markdown_path.is_file()
                with self.markdown_path.open("a", encoding="utf-8") as stream:
                    if new_file:
                        stream.write(
                            f"# Pokémon Emerald journal · trainer {self.identity}\n\n"
                        )
                    stream.write(f"- {timestamp} · {text}\n")
        except OSError:
            return

    def section(self) -> PanelSection | None:
        if not self.events:
            return None
        recent = self.events[-5:][::-1]
        rows = tuple(
            PanelRow(f"{timestamp[5:]} · {text}") for timestamp, _, text in recent
        )
        details = [PanelRow("SESSION JOURNAL")]
        if self.markdown_path is not None:
            details.append(
                PanelRow(f"Markdown copy: {self.markdown_path}", tooltip=str(self.markdown_path))
            )
        details.extend(
            PanelRow(f"{timestamp} · {text}")
            for timestamp, _, text in self.events[::-1]
        )
        return PanelSection(
            "Journal",
            rows,
            preview_limit=3,
            actions=(
                PanelAction(
                    "OPEN JOURNAL",
                    "Session Journal",
                    tuple(details),
                    key="journal-details",
                ),
            ),
            priority=55,
            role="goals",
            compact_rows=rows[:1],
            key="journal",
        )

    def _load_recent(self) -> list[tuple[str, str, str]]:
        if self.path is None or not self.path.is_file():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        events = []
        for line in lines[-MEMORY_EVENTS:]:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                events.append(
                    (
                        str(value.get("at", "")),
                        str(value.get("kind", "")),
                        str(value.get("text", "")),
                    )
                )
        return events


class EventDetector:
    """Diffs successive save observations into journal events."""

    def __init__(
        self,
        species_by_number: dict[int, str],
        flag_ids: dict[str, int],
    ) -> None:
        self._species_by_number = species_by_number
        self._flag_ids = flag_ids
        self._identity = ""
        self._caught: bytes | None = None
        self._event_flags: bytes | None = None
        self._party: dict[int, tuple[str, int]] = {}

    def reset_session(self) -> None:
        self._identity = ""
        self._caught = None
        self._event_flags = None
        self._party = {}

    def observe(
        self,
        identity: str,
        caught_flags: bytes,
        event_flags: bytes,
        party: tuple[PokemonState, ...],
    ) -> list[tuple[str, str]]:
        if identity != self._identity:
            self._identity = identity
            self._caught = caught_flags
            self._event_flags = event_flags
            self._party = self._party_levels(party)
            return []
        events: list[tuple[str, str]] = []
        events.extend(self._caught_events(caught_flags))
        events.extend(self._flag_events(event_flags))
        events.extend(self._level_events(party))
        self._caught = caught_flags
        self._event_flags = event_flags
        # Only track levels for members we can still see; an empty party read
        # keeps the previous baseline instead of re-reporting levels later.
        if party:
            self._party = self._party_levels(party)
        return events

    def _caught_events(self, caught_flags: bytes) -> list[tuple[str, str]]:
        previous = self._caught or b""
        events = []
        for index, byte in enumerate(caught_flags):
            old = previous[index] if index < len(previous) else 0
            new_bits = byte & ~old
            while new_bits:
                bit = (new_bits & -new_bits).bit_length() - 1
                new_bits &= new_bits - 1
                number = index * 8 + bit + 1
                species = self._species_by_number.get(number)
                if species is not None:
                    events.append(("caught", f"Caught {_display_species(species)}"))
        return events

    def _flag_events(self, event_flags: bytes) -> list[tuple[str, str]]:
        events = []
        for badge, name in enumerate(BADGE_NAMES):
            if self._became_set(event_flags, BADGE_FLAG_START + badge):
                events.append(("badge", f"Earned the {name}"))
        for flag_name, label in SYMBOL_FLAG_NAMES:
            flag_id = self._flag_ids.get(flag_name)
            if flag_id is not None and self._became_set(event_flags, flag_id):
                events.append(("symbol", f"Earned the {label}"))
        return events

    def _level_events(self, party: tuple[PokemonState, ...]) -> list[tuple[str, str]]:
        events = []
        for member in party:
            if member.is_egg:
                continue
            previous = self._party.get(member.personality)
            if previous is None:
                continue
            species, level = previous
            if species == member.species and member.level > level:
                events.append(
                    (
                        "level",
                        f"{_display_species(member.species)} grew to Lv {member.level}",
                    )
                )
            elif species != member.species:
                events.append(
                    (
                        "evolution",
                        f"{_display_species(species)} evolved into "
                        f"{_display_species(member.species)}",
                    )
                )
        return events

    @staticmethod
    def _party_levels(
        party: tuple[PokemonState, ...]
    ) -> dict[int, tuple[str, int]]:
        return {
            member.personality: (member.species, member.level)
            for member in party
            if not member.is_egg
        }

    def _became_set(self, event_flags: bytes, flag_id: int) -> bool:
        previous = self._event_flags or b""
        if flag_id // 8 >= len(event_flags):
            return False
        new = bool(event_flags[flag_id // 8] & (1 << (flag_id % 8)))
        old = flag_id // 8 < len(previous) and bool(
            previous[flag_id // 8] & (1 << (flag_id % 8))
        )
        return new and not old
