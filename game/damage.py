"""Gen III damage estimation from live battle state.

Follows CalculateBaseDamage() in the pinned decomp's src/pokemon.c: integer
math, physical/special split by move type, burn, stat stages, STAB, then the
type chart applied one defending type at a time and the 85-100% spread last.
Abilities, held items, screens, weather and crits are intentionally excluded;
callers must present results as estimates.
"""

from .state import BattlePokemonState, PokemonState

# Gen III splits categories by type: Normal..Steel physical, Fire.. special.
PHYSICAL_TYPES = frozenset(range(0, 9))
TYPE_MYSTERY = 9

STATUS_BURN = 1 << 4

# gStatStageRatios: stage 6 is neutral.
STAT_STAGE_RATIOS = (
    (10, 40), (10, 35), (10, 30), (10, 25), (10, 20), (10, 15),
    (10, 10),
    (15, 10), (20, 10), (25, 10), (30, 10), (35, 10), (40, 10),
)


def staged_stat(stat: int, stage: int) -> int:
    numerator, denominator = STAT_STAGE_RATIOS[max(0, min(12, stage))]
    return max(1, stat * numerator // denominator)


def type_multipliers(
    type_chart: tuple[tuple[int, int, int], ...],
    move_type: int,
    defender_types: tuple[int, ...],
) -> tuple[int, ...]:
    """Per-defending-type multipliers in tenths (0, 5, 10 or 20)."""
    chart = {
        (attack, defense): multiplier
        for attack, defense, multiplier in type_chart
    }
    return tuple(
        chart.get((move_type, defender), 10)
        for defender in dict.fromkeys(defender_types)
        if defender != TYPE_MYSTERY
    )


def damage_range(
    *,
    level: int,
    power: int,
    move_type: int,
    attacker_types: tuple[int, ...],
    attack_stat: int,
    defense_stat: int,
    multipliers: tuple[int, ...],
    burned: bool = False,
) -> tuple[int, int]:
    """Minimum and maximum damage, zero when the move cannot damage."""
    if power <= 0 or move_type == TYPE_MYSTERY or 0 in multipliers:
        return (0, 0)
    damage = (2 * level // 5 + 2) * power * attack_stat // max(1, defense_stat) // 50
    if burned and move_type in PHYSICAL_TYPES:
        damage //= 2
    damage += 2
    if move_type in attacker_types:
        damage = damage * 15 // 10
    for multiplier in multipliers:
        damage = damage * multiplier // 10
    if damage <= 0:
        return (1, 1)
    return (max(1, damage * 85 // 100), damage)


def effectiveness_value(multipliers: tuple[int, ...]) -> float:
    product = 1.0
    for multiplier in multipliers:
        product *= multiplier / 10
    return product


def attacker_offense(
    member: PokemonState,
    active_players: tuple[BattlePokemonState, ...],
    move_type: int,
) -> tuple[int, bool]:
    """Attack stat (stage-adjusted when the member is on the field) and burn."""
    physical = move_type in PHYSICAL_TYPES
    for active in active_players:
        if (
            active.personality == member.personality
            and active.species_id == member.species_id
        ):
            index = 0 if physical else 3
            return (
                staged_stat(active.stats[index], active.stat_stages[1 + index]),
                bool(active.status & STATUS_BURN),
            )
    return (
        member.stats[0] if physical else member.stats[3],
        bool(member.status & STATUS_BURN),
    )


def defender_defense(opponent: BattlePokemonState, move_type: int) -> int:
    physical = move_type in PHYSICAL_TYPES
    index = 1 if physical else 4
    return staged_stat(opponent.stats[index], opponent.stat_stages[1 + index])


def hits_to_ko(current_hp: int, minimum: int, maximum: int) -> tuple[int, int]:
    """(best case, worst case) number of hits, assuming static damage rolls."""
    if maximum <= 0:
        return (0, 0)
    best = -(-current_hp // maximum)
    worst = -(-current_hp // max(1, minimum))
    return (best, worst)
