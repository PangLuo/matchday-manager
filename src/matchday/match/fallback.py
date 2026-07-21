"""Deterministic fallback resolver — never stuck (T018; contracts/engine-interface.md).

`resolve` produces a guaranteed-legal Committed event from match state plus a local RNG
weighted by on-pitch attributes, including the legitimate NOTHING outcome. It is bound by
the same rules validate.py enforces, and is reused as the AI-vs-AI quick resolver's core
(US3). RNG is injected (seeded in tests, unseeded in live play per FR-009).
"""
from __future__ import annotations

import random

from ..models import EventType, MatchState, Side, other_side
from .validate import Committed


def _weight(state: MatchState, side: Side) -> float:
    on = state.on_pitch[side]
    if not on:
        return 0.0
    return sum(state.players[p].attack for p in on) / max(1, len(on)) + 1.0


def _pick_actor(state: MatchState, side: Side, rng: random.Random, key: str) -> str | None:
    candidates = sorted(state.on_pitch[side])
    if not candidates:
        return None
    weights = [getattr(state.players[p], key) + 1 for p in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def resolve(state: MatchState, rng: random.Random) -> Committed:
    """A guaranteed-legal event for the current state (may be NOTHING)."""
    roll = rng.random()
    if roll < 0.60:
        return Committed(EventType.NOTHING, None, None, None, "The play breaks down harmlessly.")

    # Choose the side in possession, weighted by average attack.
    wh, wa = _weight(state, "home"), _weight(state, "away")
    if wh + wa == 0:
        return Committed(EventType.NOTHING, None, None, None, "A stalemate in midfield.")
    side: Side = "home" if rng.random() < wh / (wh + wa) else "away"

    actor = _pick_actor(state, side, rng, "attack")
    if actor is None:
        return Committed(EventType.NOTHING, None, None, None, "The move fizzles out.")

    if roll < 0.80:
        return Committed(EventType.CHANCE, side, actor, None,
                         f"{state.players[actor].name} works a half-chance.")
    if roll < 0.92:
        return Committed(EventType.GOAL, side, actor, None,
                         f"{state.players[actor].name} finds the net!", score_side=side)
    # A foul, optionally on an opposition player.
    fouled = _pick_actor(state, other_side(side), rng, "defense")
    return Committed(EventType.FOUL, side, actor, fouled,
                     f"{state.players[actor].name} concedes a foul.")
