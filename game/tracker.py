import json
from pathlib import Path

from .state import BattlePokemonState, PokemonState


class BattleParticipationTracker:
    def __init__(self) -> None:
        self.participants: set[int] = set()
        self._last_turn = -1

    def update(
        self,
        party: tuple[PokemonState, ...],
        active_player_mons: tuple[BattlePokemonState, ...],
        turn: int,
    ) -> frozenset[int]:
        if turn < self._last_turn:
            self.participants.clear()
        self._last_turn = turn
        for active in active_player_mons:
            match = next(
                (
                    member
                    for member in party
                    if member.personality == active.personality
                    and member.species_id == active.species_id
                ),
                None,
            )
            if match is not None:
                self.participants.add(match.slot)
        return frozenset(self.participants)

    def end(self) -> None:
        self.participants.clear()
        self._last_turn = -1


class TrainingAreaTracker:
    def __init__(self, state_directory: Path | None) -> None:
        self._state_directory = state_directory
        self.identity = ""
        self.path: Path | None = None
        self.areas: dict[str, tuple[float, str]] = {}

    def select_playthrough(self, trainer_id: int) -> None:
        identity = f"{trainer_id:08x}"
        if identity == self.identity:
            return
        self.identity = identity
        self.path = (
            self._state_directory / f"route-exp-{identity}.json"
            if self._state_directory is not None
            else None
        )
        self.areas = self._load()

    def observe(self, method: str, average_exp: float, location: str) -> bool:
        previous = self.areas.get(method)
        if previous is not None and average_exp <= previous[0]:
            return False
        self.areas[method] = (average_exp, location)
        return True

    def save(self) -> None:
        if self.path is None:
            return
        document = {
            "schema_version": 2,
            "playthrough": self.identity,
            "best_training_areas": {
                method: {"average_exp": average_exp, "location": location}
                for method, (average_exp, location) in self.areas.items()
            },
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

    def _load(self) -> dict[str, tuple[float, str]]:
        if self.path is None or not self.path.is_file():
            return {}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if document.get("schema_version") != 2 or document.get("playthrough") != self.identity:
            return {}
        entries = document.get("best_training_areas", {})
        if not isinstance(entries, dict):
            return {}
        result = {}
        for method in ("land_mons", "water_mons", "fishing_mons"):
            value = entries.get(method)
            if not isinstance(value, dict):
                continue
            average_exp = value.get("average_exp")
            location = value.get("location")
            if (
                isinstance(average_exp, (int, float))
                and average_exp > 0
                and isinstance(location, str)
                and location
            ):
                result[method] = (float(average_exp), location)
        return result