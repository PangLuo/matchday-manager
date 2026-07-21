"""Lineup validation and auto-selection (T013; FR-004/005/006).

`validate_lineup` returns a list of explained rejections (empty = valid). `auto_lineup`
picks a legal lineup for an AI side from its available players.
"""
from __future__ import annotations

from collections import Counter

from .formations import get_formation
from .models import (
    AvailabilityStatus,
    Formation,
    Lineup,
    Player,
    Position,
    Team,
)

BENCH_SIZE = 7


def _available(player_id: str, availability: dict[str, AvailabilityStatus]) -> bool:
    status = availability.get(player_id)
    return status is None or status.is_available()


def validate_lineup(lineup: Lineup, availability: dict[str, AvailabilityStatus]) -> list[str]:
    """Return explained rejection reasons; an empty list means the lineup is legal."""
    errors: list[str] = []
    starters, bench = lineup.starters, lineup.bench

    if len(starters) != 11:
        errors.append(f"must field exactly 11 starters (got {len(starters)})")

    need = Counter(slot for slot in lineup.formation.slots)
    have = Counter(p.position for p in starters)
    if need != have:
        errors.append(
            f"formation {lineup.formation.name} needs "
            f"{ {k.value: v for k, v in need.items()} }, got "
            f"{ {k.value: v for k, v in have.items()} }"
        )

    ids = [p.id for p in starters] + [p.id for p in bench]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        errors.append(f"player selected more than once: {dups}")

    for p in starters + bench:
        if not _available(p.id, availability):
            status = availability.get(p.id)
            state = status.state.value if status else "UNKNOWN"
            errors.append(f"{p.name} is not available ({state})")

    return errors


def auto_lineup(
    team: Team,
    availability: dict[str, AvailabilityStatus],
    formation_name: str = "4-3-3",
) -> Lineup:
    """Pick a legal XI + bench for an AI side: best-rated available player per slot."""
    formation: Formation = get_formation(formation_name)
    pool = [p for p in team.players if _available(p.id, availability)]
    by_pos: dict[Position, list[Player]] = {pos: [] for pos in Position}
    for p in sorted(pool, key=lambda x: x.rating, reverse=True):
        by_pos[p.position].append(p)

    starters: list[Player] = []
    cursor = {pos: 0 for pos in Position}
    for slot in formation.slots:
        candidates = by_pos[slot]
        if cursor[slot] >= len(candidates):
            raise ValueError(f"{team.name} lacks an available {slot.value} for {formation_name}")
        starters.append(candidates[cursor[slot]])
        cursor[slot] += 1

    chosen = {p.id for p in starters}
    bench = [p for p in sorted(pool, key=lambda x: x.rating, reverse=True)
             if p.id not in chosen][:BENCH_SIZE]
    return Lineup(formation=formation, starters=starters, bench=bench)
