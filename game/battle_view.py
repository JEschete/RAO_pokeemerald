from retroarch_overlay.core.contracts import MemoryReader
from retroarch_overlay.models import GameDisplaySpec, OverlaySnapshot, PanelRow, PanelSection

from .battle import BALLS, ball_multiplier, catch_probability
from .presenter import EmeraldPresenter, display_constant
from .state import BattlePokemonState, PokemonState, decode_battle_pokemon, decode_party
from .tracker import BattleParticipationTracker


BATTLE_TYPE_FLAGS_ADDRESS = 0x02022FEC
BATTLERS_COUNT_ADDRESS = 0x0202406C
BATTLE_MONS_ADDRESS = 0x02024084
BATTLE_RESULTS_TURN_ADDRESS = 0x03005D23
MAIN_IN_BATTLE_ADDRESS = 0x030026F9
MAIN_IN_BATTLE_MASK = 0x02
BATTLE_TYPE_TRAINER = 1 << 3
BATTLE_MON_SIZE = 0x58
BALL_POCKET_OFFSET = 0x650
BALL_POCKET_SIZE = 64
SECURITY_KEY_OFFSET = 0xAC
ENEMY_PARTY_COUNT_ADDRESS = 0x020244EA
ENEMY_PARTY_ADDRESS = 0x02024744
POKEMON_SIZE = 0x64
PARTY_SIZE = 6

TYPE_NAMES = (
    "Normal", "Fighting", "Flying", "Poison", "Ground", "Rock", "Bug",
    "Ghost", "Steel", "Mystery", "Fire", "Water", "Grass", "Electric",
    "Psychic", "Ice", "Dragon", "Dark",
)


class BattleSnapshotBuilder:
    def __init__(
        self,
        species_by_id: dict[int, str],
        national_dex: dict[str, int],
        catch_rates: dict[str, int],
        presenter: EmeraldPresenter,
        tracker: BattleParticipationTracker,
        display_spec: GameDisplaySpec,
    ) -> None:
        self._species_by_id = species_by_id
        self._national_dex = national_dex
        self._catch_rates = catch_rates
        self._presenter = presenter
        self._tracker = tracker
        self._display_spec = display_spec

    def snapshot(
        self,
        memory: MemoryReader,
        save_block_1: int,
        save_block_2: int,
        caught_flags: bytes,
        map_name: str,
        location: str,
        party: tuple[PokemonState, ...],
    ) -> OverlaySnapshot | None:
        if not memory.read_memory(MAIN_IN_BATTLE_ADDRESS, 1)[0] & MAIN_IN_BATTLE_MASK:
            self._tracker.end()
            return None
        battlers_count = int.from_bytes(
            memory.read_memory(BATTLERS_COUNT_ADDRESS, 2), "little"
        )
        if battlers_count not in {2, 4}:
            return None
        battle_mons = memory.read_memory(
            BATTLE_MONS_ADDRESS, BATTLE_MON_SIZE * battlers_count
        )
        opponents = self._battlers(
            battle_mons,
            (1, 3) if battlers_count == 4 else (1,),
        )
        if not opponents:
            return None
        active_players = self._battlers(
            battle_mons,
            (0, 2) if battlers_count == 4 else (0,),
        )
        turns = memory.read_memory(BATTLE_RESULTS_TURN_ADDRESS, 1)[0]
        participants = self._tracker.update(party, active_players, turns)
        sections = [
            PanelSection(
                "Battle",
                tuple(
                    PanelRow(
                        f"{display_constant(opponent.species, 'SPECIES_')}  Lv {opponent.level}  "
                        f"HP {opponent.hp}/{opponent.max_hp}  "
                        f"{'/'.join(dict.fromkeys(TYPE_NAMES[value] for value in opponent.types if value < len(TYPE_NAMES)))}"
                        f"{self._status_text(opponent.status) if opponent.hp else ' · FNT'}"
                    )
                    for opponent in opponents
                ),
                priority=1,
                role="urgent",
            )
        ]
        battle_flags = int.from_bytes(
            memory.read_memory(BATTLE_TYPE_FLAGS_ADDRESS, 4), "little"
        )
        trainer_battle = bool(battle_flags & BATTLE_TYPE_TRAINER)
        enemy_party = self._read_enemy_party(memory)
        for section in (
            self._presenter.battle_advice_section(opponents, enemy_party, party),
            self._presenter.opponent_team_section(enemy_party),
            self._presenter.battle_reward_section(
                opponents,
                party,
                participants,
                trainer_battle=trainer_battle,
            ),
        ):
            if section is not None:
                sections.append(section)
        if not trainer_battle:
            sections.extend(
                self._catch_sections(
                    memory,
                    save_block_1,
                    save_block_2,
                    caught_flags,
                    map_name,
                    turns,
                    opponents,
                )
            )
        return OverlaySnapshot(
            "Pokémon Emerald",
            f"Battle · {location}",
            tuple(sections),
            supports_caught_filter=True,
            display_spec=self._display_spec,
        )

    def _battlers(
        self, data: bytes, indexes: tuple[int, ...]
    ) -> tuple[BattlePokemonState, ...]:
        result = []
        for battler in indexes:
            offset = BATTLE_MON_SIZE * battler
            state = decode_battle_pokemon(
                data[offset : offset + BATTLE_MON_SIZE], self._species_by_id
            )
            if state is not None:
                result.append(state)
        return tuple(result)

    def _read_enemy_party(self, memory: MemoryReader) -> tuple[PokemonState, ...]:
        count = min(memory.read_memory(ENEMY_PARTY_COUNT_ADDRESS, 1)[0], PARTY_SIZE)
        data = memory.read_memory(ENEMY_PARTY_ADDRESS, POKEMON_SIZE * count)
        return decode_party(data, count, self._species_by_id)

    def _catch_sections(
        self,
        memory: MemoryReader,
        save_block_1: int,
        save_block_2: int,
        caught_flags: bytes,
        map_name: str,
        turns: int,
        opponents: tuple[BattlePokemonState, ...],
    ) -> tuple[PanelSection, ...]:
        quantities = self._ball_quantities(memory, save_block_1, save_block_2)
        sections = []
        for opponent in opponents:
            catch_rate = self._catch_rates.get(opponent.species)
            chances = []
            if catch_rate is not None and opponent.hp:
                for ball in BALLS:
                    quantity = quantities.get(ball.item_id, 0)
                    if not quantity:
                        continue
                    multiplier = ball_multiplier(
                        ball.item_id,
                        level=opponent.level,
                        types=opponent.types,
                        caught=self._is_caught(opponent.species, caught_flags),
                        underwater=map_name.startswith("Underwater_"),
                        turns=turns,
                    )
                    probability = catch_probability(
                        catch_rate,
                        opponent.hp,
                        opponent.max_hp,
                        opponent.status,
                        multiplier,
                        master_ball=ball.item_id == 1,
                    )
                    chances.append(
                        (probability, PanelRow(f"{ball.name} x{quantity}  {probability:.1%}"))
                    )
            if chances:
                title = "Catch chances"
                if len(opponents) > 1:
                    title += f" · {display_constant(opponent.species, 'SPECIES_')}"
                sections.append(
                    PanelSection(
                        title,
                        tuple(
                            row
                            for _, row in sorted(
                                chances, reverse=True, key=lambda entry: entry[0]
                            )
                        ),
                        priority=6,
                        role="urgent",
                    )
                )
        return tuple(sections)

    @staticmethod
    def _ball_quantities(
        memory: MemoryReader,
        save_block_1: int,
        save_block_2: int,
    ) -> dict[int, int]:
        key = int.from_bytes(
            memory.read_memory(save_block_2 + SECURITY_KEY_OFFSET, 2), "little"
        )
        pocket = memory.read_memory(
            save_block_1 + BALL_POCKET_OFFSET, BALL_POCKET_SIZE
        )
        quantities = {}
        for offset in range(0, len(pocket), 4):
            item_id = int.from_bytes(pocket[offset : offset + 2], "little")
            encrypted = int.from_bytes(pocket[offset + 2 : offset + 4], "little")
            if item_id:
                quantities[item_id] = encrypted ^ key
        return quantities

    def _is_caught(self, species: str, caught_flags: bytes) -> bool:
        number = self._national_dex[species]
        bit = number - 1
        return bool(caught_flags[bit // 8] & (1 << (bit % 8)))

    @staticmethod
    def _status_text(status: int) -> str:
        for mask, label in (
            (0x7, "SLP"),
            (0x8, "PSN"),
            (0x10, "BRN"),
            (0x20, "FRZ"),
            (0x40, "PAR"),
            (0x80, "TOX"),
        ):
            if status & mask:
                return f" · {label}"
        return ""