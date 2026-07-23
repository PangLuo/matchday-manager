"""The discrete-moment engine (T019; contracts/engine-interface.md).

Per moment: provider.propose → validate → commit, with MAX_RETRIES then the deterministic
fallback (never stuck). Code stamps period/minute/moment_index/score/source; the model
never writes authoritative counters. US1 runs the regulation lifecycle for managed group
matches; US2 adds substitution windows and US3 adds extra time / shootouts.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..models import (
    EventSource,
    EventType,
    Lineup,
    MatchEvent,
    MatchPeriod,
    MatchResult,
    MatchState,
    Phase,
    Player,
    Side,
    other_side,
)
from .fallback import resolve as fallback_resolve
from .provider import EventProvider, ProviderError
from .validate import Committed, Ok, validate

MAX_RETRIES = 2

# Discrete moment minutes per half (markers occupy 0/45/90).
_FIRST_HALF = [5, 10, 15, 20, 25, 30, 35, 40]
_SECOND_HALF = [50, 55, 60, 65, 70, 75, 80, 85]


@dataclass
class MatchOutcome:
    events: list[MatchEvent]
    result: MatchResult
    log: list[dict] = field(default_factory=list)   # engine I/O log entries
    degraded: bool = False                            # any moment fell back to the resolver


def build_match_state(
    home_lineup: Lineup,
    away_lineup: Lineup,
    home_team_id: str,
    away_team_id: str,
    phase: Phase = Phase.GROUP,
) -> MatchState:
    players: dict[str, Player] = {}
    side_of: dict[str, Side] = {}
    on_pitch: dict[Side, set[str]] = {"home": set(), "away": set()}
    bench: dict[Side, set[str]] = {"home": set(), "away": set()}

    for side, lineup in (("home", home_lineup), ("away", away_lineup)):
        for p in lineup.starters:
            players[p.id] = p
            side_of[p.id] = side
            on_pitch[side].add(p.id)
        for p in lineup.bench:
            players[p.id] = p
            side_of[p.id] = side
            bench[side].add(p.id)

    return MatchState(
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        phase=phase,
        players=players,
        side_of=side_of,
        on_pitch=on_pitch,
        bench=bench,
        used={"home": set(), "away": set()},
        subs_used={"home": 0, "away": 0},
    )


def _marker(etype: EventType, commentary: str) -> Committed:
    return Committed(etype, None, None, None, commentary)


def _commit(state: MatchState, c: Committed, source: EventSource,
            minute: int, moment_index: int) -> MatchEvent:
    state.minute = minute
    state.moment_index = moment_index
    if c.advance_period is not None:
        state.current_period = c.advance_period
    if c.score_side is not None:
        state.score[c.score_side] += 1
    if c.shootout_side is not None:
        state.shootout[c.shootout_side] += 1
    event = MatchEvent(
        moment_index=moment_index,
        minute=minute,
        type=c.type,
        commentary=c.commentary,
        team_side=c.team_side,
        actor_id=c.actor_id,
        secondary_id=c.secondary_id,
        period=state.current_period,
        source=source,
    )
    state.history.append(event)   # the model reads the full match so far (prompt.py)
    return event


def _resolve_moment(
    state: MatchState,
    provider: EventProvider,
    prompt_version: str,
    fallback_rng: random.Random,
    log: list[dict],
) -> tuple[Committed, EventSource]:
    rejections: list[str] = []
    for _ in range(MAX_RETRIES + 1):
        result = provider.propose(state, prompt_version)
        if isinstance(result, ProviderError):
            rejections.append(f"provider_error: {result.message}")
            continue
        decision = validate(result, state)
        if isinstance(decision, Ok):
            log.append({"minute": state.minute, "prompt_version": prompt_version,
                        "source": "MODEL", "type": decision.value.type.value,
                        "rejections": rejections})
            return decision.value, EventSource.MODEL
        rejections.append(decision.reason)
    committed = fallback_resolve(state, fallback_rng)
    log.append({"minute": state.minute, "prompt_version": prompt_version,
                "source": "FALLBACK", "type": committed.type.value, "rejections": rejections})
    return committed, EventSource.FALLBACK


def simulate_match(
    state: MatchState,
    provider: EventProvider,
    *,
    prompt_version: str = "v1",
    fallback_rng: Optional[random.Random] = None,
    on_event: Optional[Callable[[MatchEvent], None]] = None,
) -> MatchOutcome:
    """Play a managed regulation match to the final whistle (US1)."""
    fallback_rng = fallback_rng or random.Random()
    events: list[MatchEvent] = []
    log: list[dict] = []
    degraded = False
    idx = 0

    def emit(c: Committed, source: EventSource, minute: int) -> None:
        nonlocal idx
        ev = _commit(state, c, source, minute, idx)
        events.append(ev)
        idx += 1
        if on_event is not None:
            on_event(ev)

    emit(_marker(EventType.KICKOFF, "Kick-off!"), EventSource.MODEL, 0)
    for phase_minutes, half_marker in (
        (_FIRST_HALF, (EventType.HALF_TIME, 45, "Half-time.")),
        (_SECOND_HALF, (EventType.FULL_TIME, 90, "Full-time.")),
    ):
        for minute in phase_minutes:
            state.minute = minute
            # Per-moment luck nudge (research R2): signed, + favours home, - favours away.
            # Drawn from the one injected RNG so live play varies and tests stay reproducible.
            state.luck = round(fallback_rng.uniform(-1.0, 1.0), 2)
            c, source = _resolve_moment(state, provider, prompt_version, fallback_rng, log)
            degraded = degraded or source == EventSource.FALLBACK
            emit(c, source, minute)
        mtype, mminute, mtext = half_marker
        emit(_marker(mtype, mtext), EventSource.MODEL, mminute)

    emit(_marker(EventType.FINAL_WHISTLE, "The final whistle blows."), EventSource.MODEL, 90)

    result = MatchResult(
        home=state.score["home"],
        away=state.score["away"],
        winner=_winner(state.score),
        decided_by="normal",
    )
    return MatchOutcome(events=events, result=result, log=log, degraded=degraded)


def _winner(score: dict[Side, int]) -> Optional[Side]:
    if score["home"] > score["away"]:
        return "home"
    if score["away"] > score["home"]:
        return "away"
    return None


def build_report(outcome: MatchOutcome, home_name: str, away_name: str,
                 players: dict[str, Player]) -> str:
    """A short post-match report: final score plus scorers (FR-008)."""
    r = outcome.result
    lines = [f"FULL-TIME: {home_name} {r.home} - {r.away} {away_name}"]
    scorers: list[str] = []
    for ev in outcome.events:
        if ev.type == EventType.GOAL and ev.actor_id:
            scorers.append(f"  {ev.minute}' {players[ev.actor_id].name} ({_side_name(ev.team_side, home_name, away_name)})")
        elif ev.type == EventType.OWN_GOAL and ev.actor_id:
            scorers.append(f"  {ev.minute}' {players[ev.actor_id].name} (o.g.)")
    if scorers:
        lines.append("Goals:")
        lines.extend(scorers)
    if outcome.degraded:
        lines.append("(some moments were resolved by the offline fallback engine)")
    return "\n".join(lines)


def _side_name(side: Optional[Side], home_name: str, away_name: str) -> str:
    return home_name if side == "home" else away_name if side == "away" else "?"
