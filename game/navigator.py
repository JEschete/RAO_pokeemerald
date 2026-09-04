from collections import deque
from dataclasses import dataclass

from retroarch_overlay.models import PanelAction, PanelRow, PanelSection


@dataclass(frozen=True, slots=True)
class Objective:
    title: str
    flag: str
    map_name: str
    detail: str
    requires: tuple[str, ...] = ()


MAIN_STORY = (
    Objective("Earn the Stone Badge", "FLAG_DEFEATED_RUSTBORO_GYM", "RustboroCity_Gym", "Challenge Roxanne in Rustboro Gym."),
    Objective("Deliver Steven's letter", "FLAG_DELIVERED_STEVEN_LETTER", "GraniteCave_StevensRoom", "Find Steven at the back of Granite Cave."),
    Objective("Deliver the Devon Goods", "FLAG_DELIVERED_DEVON_GOODS", "SlateportCity_OceanicMuseum_2F", "Take the Devon Goods to Captain Stern."),
    Objective("Earn the Dynamo Badge", "FLAG_DEFEATED_MAUVILLE_GYM", "MauvilleCity_Gym", "Challenge Wattson in Mauville Gym."),
    Objective("Stop the Mt. Chimney team", "FLAG_DEFEATED_EVIL_TEAM_MT_CHIMNEY", "MtChimney", "Confront Team Magma at the summit."),
    Objective("Earn the Heat Badge", "FLAG_DEFEATED_LAVARIDGE_GYM", "LavaridgeTown_Gym_1F", "Challenge Flannery in Lavaridge Gym."),
    Objective("Earn the Balance Badge", "FLAG_DEFEATED_PETALBURG_GYM", "PetalburgCity_Gym", "Return to Petalburg and challenge Norman."),
    Objective("Clear the Weather Institute", "FLAG_RECEIVED_CASTFORM", "Route119_WeatherInstitute_2F", "Defeat Team Aqua and receive Castform."),
    Objective("Receive the Devon Scope", "FLAG_RECEIVED_DEVON_SCOPE", "Route120", "Meet Steven and reveal the invisible Kecleon."),
    Objective("Earn the Feather Badge", "FLAG_DEFEATED_FORTREE_GYM", "FortreeCity_Gym", "Challenge Winona in Fortree Gym."),
    Objective("Recover the Mt. Pyre orb", "FLAG_RECEIVED_RED_OR_BLUE_ORB", "MtPyre_Summit", "Climb Mt. Pyre after Team Aqua."),
    Objective("Earn the Mind Badge", "FLAG_DEFEATED_MOSSDEEP_GYM", "MossdeepCity_Gym", "Challenge Tate and Liza."),
    Objective("Defend the Space Center", "FLAG_DEFEATED_MAGMA_SPACE_CENTER", "MossdeepCity_SpaceCenter_2F", "Help Steven stop Team Magma."),
    Objective("Resolve the weather crisis", "FLAG_SOOTOPOLIS_ARCHIE_MAXIE_LEAVE", "SootopolisCity", "Awaken Rayquaza and return to Sootopolis."),
    Objective("Earn the Rain Badge", "FLAG_DEFEATED_SOOTOPOLIS_GYM", "SootopolisCity_Gym_1F", "Challenge Juan in Sootopolis Gym."),
    Objective("Enter the Hall of Fame", "FLAG_SYS_GAME_CLEAR", "EverGrandeCity_HallOfFame", "Defeat the Elite Four and Champion Wallace."),
)


SIDEQUESTS = (
    Objective("Pick up the Wailmer Pail", "FLAG_RECEIVED_WAILMER_PAIL", "Route104_PrettyPetalFlowerShop", "Speak to the flower shop owner."),
    Objective("Choose a bicycle", "FLAG_RECEIVED_BIKE", "MauvilleCity_BikeShop", "Visit Rydel's Cycles."),
    Objective("Collect the Old Rod", "FLAG_RECEIVED_OLD_ROD", "DewfordTown", "Speak to the fisherman near the Gym."),
    Objective("Collect the Good Rod", "FLAG_RECEIVED_GOOD_ROD", "Route118", "Speak to the fisherman by the shore."),
    Objective("Collect the Super Rod", "FLAG_RECEIVED_SUPER_ROD", "MossdeepCity_House3", "Speak to the fisherman in Mossdeep."),
    Objective("Collect the Pokéblock Case", "FLAG_RECEIVED_POKEBLOCK_CASE", "SlateportCity_ContestLobby", "Visit the Slateport Contest Hall."),
    Objective("Collect the Powder Jar", "FLAG_RECEIVED_POWDER_JAR", "SlateportCity", "Speak to the Berry Crush fan after obtaining the Pokéblock Case.", ("FLAG_RECEIVED_POKEBLOCK_CASE",)),
    Objective("Explore New Mauville", "FLAG_GOT_BASEMENT_KEY_FROM_WATTSON", "MauvilleCity", "Speak to Wattson after the Balance Badge.", ("FLAG_DEFEATED_PETALBURG_GYM",)),
    Objective("Exchange the Scanner", "FLAG_EXCHANGED_SCANNER", "SlateportCity_Harbor", "Recover the Scanner from the Abandoned Ship and take it to Captain Stern.", ("FLAG_DEFEATED_PETALBURG_GYM",)),
    Objective("Receive Beldum", "FLAG_RECEIVED_BELDUM", "MossdeepCity_StevensHouse", "Visit Steven's house after entering the Hall of Fame.", ("FLAG_SYS_GAME_CLEAR",)),
)


class ObjectiveNavigator:
    def __init__(self, flag_ids: dict[str, int], graph: dict[str, list[str]]) -> None:
        self._flag_ids = flag_ids
        self._graph = {name: tuple(neighbors) for name, neighbors in graph.items()}

    def section(self, current_map: str, flags: bytes) -> PanelSection | None:
        next_story = next(
            (goal for goal in MAIN_STORY if not self._complete(goal, flags)),
            None,
        )
        available_sidequests = [
            goal
            for goal in SIDEQUESTS
            if not self._complete(goal, flags)
            and all(self._flag_set(flags, requirement) for requirement in goal.requires)
        ]
        if next_story is None and not available_sidequests:
            return None
        distances = self._distances(current_map)
        available_sidequests.sort(
            key=lambda goal: (distances.get(goal.map_name, 9999), goal.title)
        )
        rows = []
        if next_story is not None:
            rows.append(
                PanelRow(
                    f"Next story · {next_story.title} · "
                    f"{self._proximity(next_story.map_name, distances)}"
                )
            )
        rows.extend(
            PanelRow(
                f"Optional · {goal.title} · {self._proximity(goal.map_name, distances)}"
            )
            for goal in available_sidequests[:2]
        )
        details = []
        if next_story is not None:
            details.extend(
                (
                    PanelRow("NEXT STORY GOAL"),
                    PanelRow(next_story.title),
                    PanelRow(next_story.detail),
                    PanelRow(self._location_line(next_story.map_name, distances)),
                )
            )
        if available_sidequests:
            details.append(PanelRow("NEARBY OPTIONAL GOALS"))
            for goal in available_sidequests:
                details.append(PanelRow(f"{goal.title} · {self._location_line(goal.map_name, distances)}"))
                details.append(PanelRow(goal.detail))
        return PanelSection(
            "Navigator",
            tuple(rows),
            actions=(PanelAction("OPEN NAVIGATOR", "Story and Sidequests", tuple(details)),),
            priority=8,
            role="goals",
            compact_rows=tuple(rows[:2]),
        )

    def _complete(self, goal: Objective, flags: bytes) -> bool:
        return self._flag_set(flags, goal.flag)

    def _flag_set(self, flags: bytes, name: str) -> bool:
        flag_id = self._flag_ids.get(name)
        return (
            flag_id is not None
            and flag_id // 8 < len(flags)
            and bool(flags[flag_id // 8] & (1 << (flag_id % 8)))
        )

    def _distances(self, start: str) -> dict[str, int]:
        if start not in self._graph:
            return {}
        distances = {start: 0}
        pending = deque((start,))
        while pending:
            current = pending.popleft()
            for neighbor in self._graph.get(current, ()):
                if neighbor in distances:
                    continue
                distances[neighbor] = distances[current] + 1
                pending.append(neighbor)
        return distances

    @staticmethod
    def _proximity(map_name: str, distances: dict[str, int]) -> str:
        distance = distances.get(map_name)
        if distance == 0:
            return "here"
        if distance == 1:
            return "1 transition away"
        if distance is not None:
            return f"{distance} transitions away"
        return "location unavailable"

    def _location_line(self, map_name: str, distances: dict[str, int]) -> str:
        label = " · ".join(
            part.replace("Pokemon", "Pokémon")
            for part in map_name.replace("_", " ").split(" · ")
        )
        return f"{label} · {self._proximity(map_name, distances)}"