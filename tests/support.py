"""Shared test helpers (no network, deterministic)."""
from __future__ import annotations

from matchday.models import (
    MatchPeriod,
    MatchState,
    Phase,
    Player,
    Position,
    Side,
)


def make_player(pid: str, pos: Position = Position.MID, **kw) -> Player:
    return Player(id=pid, name=pid, position=pos, **kw)


def build_state(
    home_ids: list[str] | None = None,
    away_ids: list[str] | None = None,
    home_bench: list[str] | None = None,
    away_bench: list[str] | None = None,
    phase: Phase = Phase.GROUP,
) -> MatchState:
    """A minimal live MatchState with the given on-pitch and bench player ids."""
    home_ids = home_ids or [f"h{i}" for i in range(1, 12)]
    away_ids = away_ids or [f"a{i}" for i in range(1, 12)]
    home_bench = home_bench or []
    away_bench = away_bench or []

    players: dict[str, Player] = {}
    side_of: dict[str, Side] = {}
    for pid in home_ids + home_bench:
        players[pid] = make_player(pid)
        side_of[pid] = "home"
    for pid in away_ids + away_bench:
        players[pid] = make_player(pid)
        side_of[pid] = "away"

    return MatchState(
        home_team_id="HOME",
        away_team_id="AWAY",
        phase=phase,
        players=players,
        side_of=side_of,
        on_pitch={"home": set(home_ids), "away": set(away_ids)},
        bench={"home": set(home_bench), "away": set(away_bench)},
        used={"home": set(), "away": set()},
        subs_used={"home": 0, "away": 0},
        current_period=MatchPeriod.REGULATION,
    )
