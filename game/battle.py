from dataclasses import dataclass
from math import sqrt

from .state import PokemonState


@dataclass(frozen=True, slots=True)
class Ball:
    item_id: int
    name: str


BALLS = (
    Ball(1, "Master Ball"),
    Ball(2, "Ultra Ball"),
    Ball(3, "Great Ball"),
    Ball(4, "Poké Ball"),
    Ball(6, "Net Ball"),
    Ball(7, "Dive Ball"),
    Ball(8, "Nest Ball"),
    Ball(9, "Repeat Ball"),
    Ball(10, "Timer Ball"),
    Ball(11, "Luxury Ball"),
    Ball(12, "Premier Ball"),
)

TYPE_WATER = 11
TYPE_BUG = 6
STATUS_SLEEP = 1 << 0
STATUS_POISON = 1 << 3
STATUS_BURN = 1 << 4
STATUS_FREEZE = 1 << 5
STATUS_PARALYSIS = 1 << 6
STATUS_TOXIC_POISON = 1 << 7
ITEM_MACHO_BRACE = 181
ITEM_EXP_SHARE = 182
ITEM_LUCKY_EGG = 197


def ball_multiplier(
    item_id: int,
    *,
    level: int,
    types: tuple[int, int],
    caught: bool,
    underwater: bool,
    turns: int,
) -> int:
    if item_id == 2:
        return 20
    if item_id == 3:
        return 15
    if item_id in {1, 4, 11, 12}:
        return 10
    if item_id == 6:
        return 30 if TYPE_WATER in types or TYPE_BUG in types else 10
    if item_id == 7:
        return 35 if underwater else 10
    if item_id == 8:
        return max(10, 40 - level) if level < 40 else 10
    if item_id == 9:
        return 30 if caught else 10
    if item_id == 10:
        return min(40, turns + 10)
    raise ValueError(f"Unsupported Poké Ball item ID: {item_id}")


def catch_probability(
    catch_rate: int,
    current_hp: int,
    max_hp: int,
    status: int,
    multiplier: int,
    *,
    master_ball: bool = False,
) -> float:
    if master_ball:
        return 1.0
    if catch_rate <= 0 or max_hp <= 0 or current_hp <= 0:
        return 0.0

    odds = (catch_rate * multiplier // 10) * (max_hp * 3 - current_hp * 2) // (3 * max_hp)
    if status & (STATUS_SLEEP | STATUS_FREEZE):
        odds *= 2
    if status & (
        STATUS_POISON | STATUS_BURN | STATUS_PARALYSIS | STATUS_TOXIC_POISON
    ):
        odds = odds * 15 // 10
    if odds > 254:
        return 1.0
    if odds <= 0:
        return 0.0

    shake_threshold = 1048560 / sqrt(sqrt(16711680 / odds))
    return min(1.0, (shake_threshold / 65536) ** 4)


def experience_awards(
    exp_yield: int,
    opponent_level: int,
    party: tuple[PokemonState, ...],
    participants: frozenset[int],
    *,
    trainer_battle: bool,
) -> dict[int, int]:
    eligible_participants = tuple(
        member
        for member in party
        if member.slot in participants and member.hp > 0 and not member.is_egg
    )
    share_holders = tuple(
        member
        for member in party
        if member.held_item_id == ITEM_EXP_SHARE and member.hp > 0 and not member.is_egg
    )
    if not eligible_participants and not share_holders:
        return {}
    calculated = exp_yield * opponent_level // 7
    if share_holders:
        sent_share = max(1, calculated // 2 // len(eligible_participants)) if eligible_participants else 0
        held_share = max(1, calculated // 2 // len(share_holders))
    else:
        sent_share = max(1, calculated // len(eligible_participants)) if eligible_participants else 0
        held_share = 0
    awards = {}
    for member in party:
        value = sent_share if member.slot in participants and member.hp > 0 and not member.is_egg else 0
        if member in share_holders:
            value += held_share
        if not value:
            continue
        if member.held_item_id == ITEM_LUCKY_EGG:
            value = value * 150 // 100
        if trainer_battle:
            value = value * 150 // 100
        if member.is_traded:
            value = value * 150 // 100
        awards[member.slot] = value
    return awards


def ev_awards(
    ev_yield: tuple[int, int, int, int, int, int],
    party: tuple[PokemonState, ...],
    participants: frozenset[int],
) -> dict[int, tuple[int, int, int, int, int, int]]:
    recipients = {
        member.slot
        for member in party
        if member.hp > 0
        and not member.is_egg
        and (member.slot in participants or member.held_item_id == ITEM_EXP_SHARE)
    }
    awards = {}
    for member in party:
        if member.slot not in recipients:
            continue
        multiplier = 2 if member.pokerus else 1
        if member.held_item_id == ITEM_MACHO_BRACE:
            multiplier *= 2
        total = sum(member.evs)
        gains = []
        for current, base_gain in zip(member.evs, ev_yield):
            room = min(255 - current, 510 - total)
            gain = max(0, min(base_gain * multiplier, room))
            gains.append(gain)
            total += gain
        awards[member.slot] = tuple(gains)
    return awards