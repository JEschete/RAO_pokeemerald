from retroarch_overlay.core.contracts import MemoryReader
from retroarch_overlay.models import (
    GameDisplaySpec,
    OverlaySnapshot,
    PanelChip,
    PanelRow,
    PanelSection,
)

from .battle import (
    BALLS,
    STATUS_FREEZE,
    STATUS_SLEEP,
    ball_multiplier,
    catch_probability,
)
from .hunt import HuntTracker
from .presenter import (
    EmeraldPresenter,
    display_constant,
    status_chips,
    type_chip,
)
from .state import (
    BattlePokemonState,
    PokemonState,
    StoredPokemonState,
    decode_battle_pokemon,
    decode_party,
    decode_pokemon_storage,
)
from .tracker import BattleParticipationTracker
from .wildiv import WildScout


BATTLE_TYPE_FLAGS_ADDRESS = 0x02022FEC
BATTLERS_COUNT_ADDRESS = 0x0202406C
BATTLE_MONS_ADDRESS = 0x02024084
BATTLE_RESULTS_TURN_ADDRESS = 0x03005D23
MAIN_IN_BATTLE_ADDRESS = 0x030026F9
MAIN_IN_BATTLE_MASK = 0x02
BATTLE_TYPE_LINK = 1 << 1
BATTLE_TYPE_TRAINER = 1 << 3
BATTLE_TYPE_SAFARI = 1 << 7
BATTLE_TYPE_BATTLE_TOWER = 1 << 8
BATTLE_TYPE_EREADER_TRAINER = 1 << 11
BATTLE_TYPE_DOME = 1 << 16
BATTLE_TYPE_PALACE = 1 << 17
BATTLE_TYPE_ARENA = 1 << 18
BATTLE_TYPE_FACTORY = 1 << 19
BATTLE_TYPE_PIKE = 1 << 20
BATTLE_TYPE_PYRAMID = 1 << 21
BATTLE_TYPE_INGAME_PARTNER = 1 << 22
BATTLE_TYPE_RECORDED_LINK = 1 << 25
BATTLE_TYPE_TRAINER_HILL = 1 << 26
BATTLE_TYPE_FRONTIER = (
    BATTLE_TYPE_BATTLE_TOWER
    | BATTLE_TYPE_DOME
    | BATTLE_TYPE_PALACE
    | BATTLE_TYPE_ARENA
    | BATTLE_TYPE_FACTORY
    | BATTLE_TYPE_PIKE
    | BATTLE_TYPE_PYRAMID
)
NO_REWARD_BATTLE_TYPES = (
    BATTLE_TYPE_LINK
    | BATTLE_TYPE_RECORDED_LINK
    | BATTLE_TYPE_TRAINER_HILL
    | BATTLE_TYPE_FRONTIER
    | BATTLE_TYPE_SAFARI
    | BATTLE_TYPE_EREADER_TRAINER
)
BATTLE_MON_SIZE = 0x58
BALL_POCKET_OFFSET = 0x650
BALL_POCKET_SIZE = 64
SECURITY_KEY_OFFSET = 0xAC
ENEMY_PARTY_COUNT_ADDRESS = 0x020244EA
ENEMY_PARTY_ADDRESS = 0x02024744
POKEMON_SIZE = 0x64
PARTY_SIZE = 6
POKEMON_STORAGE_POINTER_ADDRESS = 0x03005D94
# PokemonStorage.boxes follows a u8 currentBox but BoxPokemon is u32-aligned,
# so the boxes start at 0x4 (boxNames lands at 0x8344 = 4 + 14 * 30 * 0x50).
POKEMON_STORAGE_BOXES_OFFSET = 4
POKEMON_STORAGE_BOX_COUNT = 14
POKEMON_STORAGE_SLOTS_PER_BOX = 30
POKEMON_STORAGE_SIZE = (
    POKEMON_STORAGE_BOX_COUNT * POKEMON_STORAGE_SLOTS_PER_BOX * 0x50
)
EWRAM_START = 0x02000000
EWRAM_END = 0x02040000

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
        hunt: HuntTracker | None = None,
        wild_scout: WildScout | None = None,
    ) -> None:
        self._species_by_id = species_by_id
        self._national_dex = national_dex
        self._catch_rates = catch_rates
        self._presenter = presenter
        self._tracker = tracker
        self._display_spec = display_spec
        self._hunt = hunt
        self._wild_scout = wild_scout
        self._storage_encounter: tuple[int, int] | None = None
        self._stored_pokemon: tuple[StoredPokemonState, ...] = ()
        self._storage_error = ""

    def reset_session(self) -> None:
        self._storage_encounter = None
        self._stored_pokemon = ()
        self._storage_error = ""

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
            self._finish_hunt(caught_flags, party)
            self.reset_session()
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
        battle_flags = int.from_bytes(
            memory.read_memory(BATTLE_TYPE_FLAGS_ADDRESS, 4), "little"
        )
        trainer_battle = bool(battle_flags & BATTLE_TYPE_TRAINER)
        safari_battle = bool(battle_flags & BATTLE_TYPE_SAFARI)
        rewards_available = not bool(battle_flags & NO_REWARD_BATTLE_TYPES)
        if rewards_available:
            participants = self._tracker.update(party, active_players, turns)
        else:
            self._tracker.end()
            participants = frozenset()
        if not trainer_battle and self._hunt is not None:
            self._hunt.battle_started(
                opponents[0], self._is_caught(opponents[0].species, caught_flags)
            )
        sections = [
            PanelSection(
                "Battle",
                tuple(
                    PanelRow(
                        f"{display_constant(opponent.species, 'SPECIES_')}  Lv {opponent.level}  "
                        f"HP {opponent.hp}/{opponent.max_hp}"
                        f"{'' if opponent.hp else ' · FNT'}",
                        progress=(
                            opponent.hp / opponent.max_hp
                            if opponent.max_hp
                            else None
                        ),
                        icon=self._presenter.icon_path(opponent.species),
                        chips=status_chips(opponent.status)
                        or tuple(
                            chip
                            for chip in (
                                type_chip(value)
                                for value in dict.fromkeys(opponent.types)
                            )
                            if chip is not None
                        ),
                    )
                    for opponent in opponents
                ),
                priority=1,
                role="urgent",
                key="battle",
            )
        ]
        enemy_party = self._read_enemy_party(memory)
        for section in (
            self._presenter.battle_advice_section(
                opponents, enemy_party, party, active_players
            ),
            self._presenter.opponent_team_section(enemy_party),
            (
                self._presenter.battle_reward_section(
                    opponents,
                    party,
                    participants,
                    trainer_battle=trainer_battle,
                    in_game_partner=bool(
                        battle_flags & BATTLE_TYPE_INGAME_PARTNER
                    ),
                )
                if rewards_available
                else None
            ),
        ):
            if section is not None:
                sections.append(section)
        if not trainer_battle:
            if self._wild_scout is not None and opponents:
                boxed, box_error = self._boxed_for_encounter(
                    memory,
                    opponents[0],
                )
                iv_section = self._wild_scout.section(
                    opponents[0],
                    party,
                    boxed,
                    box_error=box_error,
                )
                if iv_section is not None:
                    sections.append(iv_section)
        else:
            self.reset_session()
        if not trainer_battle and not safari_battle:
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

    def _boxed_for_encounter(
        self,
        memory: MemoryReader,
        opponent: BattlePokemonState,
    ) -> tuple[tuple[StoredPokemonState, ...], str]:
        encounter = (opponent.species_id, opponent.personality)
        if encounter == self._storage_encounter:
            return self._stored_pokemon, self._storage_error
        self._storage_encounter = encounter
        self._stored_pokemon = ()
        self._storage_error = ""
        try:
            pointer_data = memory.read_memory(
                POKEMON_STORAGE_POINTER_ADDRESS,
                4,
            )
            if len(pointer_data) != 4:
                raise ValueError("storage pointer read was incomplete")
            pointer = int.from_bytes(pointer_data, "little")
            start = pointer + POKEMON_STORAGE_BOXES_OFFSET
            if not (
                EWRAM_START <= pointer < EWRAM_END
                and start + POKEMON_STORAGE_SIZE <= EWRAM_END
            ):
                raise ValueError("storage pointer is unavailable")
            box_size = POKEMON_STORAGE_SLOTS_PER_BOX * 0x50
            chunks = []
            for box in range(POKEMON_STORAGE_BOX_COUNT):
                chunk = memory.read_memory(start + box * box_size, box_size)
                if len(chunk) != box_size:
                    raise ValueError(
                        f"box {box + 1} read was incomplete"
                    )
                chunks.append(chunk)
            self._stored_pokemon = decode_pokemon_storage(
                b"".join(chunks),
                self._species_by_id,
                box_count=POKEMON_STORAGE_BOX_COUNT,
                slots_per_box=POKEMON_STORAGE_SLOTS_PER_BOX,
            )
        except (AssertionError, OSError, RuntimeError, ValueError) as error:
            self._storage_error = str(error)
        return self._stored_pokemon, self._storage_error

    def _finish_hunt(
        self, caught_flags: bytes, party: tuple[PokemonState, ...]
    ) -> None:
        if self._hunt is None:
            return
        species = self._hunt.active_species()
        if species is None:
            return
        self._hunt.battle_ended(
            self._is_caught(species, caught_flags), party
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
        if count == 0:
            return ()
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
        for opponent_index, opponent in enumerate(opponents):
            catch_rate = self._catch_rates.get(opponent.species)
            if catch_rate is None or not opponent.hp:
                continue
            chances = []
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
                chances.append((probability, multiplier, ball, quantity))
            if not chances:
                continue
            chances.sort(reverse=True, key=lambda entry: entry[0])
            rows = [
                PanelRow(
                    f"HP {opponent.hp}/{opponent.max_hp} · lower HP and status "
                    "raise every ball",
                    progress=(
                        opponent.hp / opponent.max_hp if opponent.max_hp else None
                    ),
                    chips=status_chips(opponent.status),
                )
            ]
            for index, (probability, _, ball, quantity) in enumerate(chances):
                rows.append(
                    PanelRow(
                        f"{ball.name} x{quantity} · {probability:.1%}",
                        progress=probability,
                        progress_color="accent",
                        chips=(
                            (PanelChip("BEST", "#27824a"),)
                            if index == 0 and len(chances) > 1
                            else ()
                        ),
                    )
                )
            best_probability, best_multiplier, best_ball, _ = chances[0]
            if (
                not opponent.status & (STATUS_SLEEP | STATUS_FREEZE)
                and best_ball.item_id != 1
                and best_probability < 0.995
            ):
                asleep = catch_probability(
                    catch_rate,
                    opponent.hp,
                    opponent.max_hp,
                    STATUS_SLEEP,
                    best_multiplier,
                )
                rows.append(
                    PanelRow(
                        f"Asleep, {best_ball.name} would reach {asleep:.1%}",
                        emphasis="muted",
                    )
                )
            if self._hunt is not None:
                stats = self._hunt.stats_for(opponent.species)
                if stats is not None:
                    rows.append(
                        PanelRow(
                            f"Lifetime · seen {stats['seen']} · caught "
                            f"{stats['caught']} · KO {stats['ko']} · fled "
                            f"{stats['fled']}",
                            emphasis="muted",
                        )
                    )
            title = "Catch chances"
            if len(opponents) > 1:
                title += f" · {display_constant(opponent.species, 'SPECIES_')}"
            sections.append(
                PanelSection(
                    title,
                    tuple(rows),
                    priority=6,
                    role="urgent",
                    compact_rows=(rows[1],),
                    key=f"catch-chances-{opponent_index}",
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
