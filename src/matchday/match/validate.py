"""Event validation contract — code owns truth (T017; contracts/event-schema.md §2).

`validate` is the sole path from a proposed event to committed state. It is pure: it never
mutates `state`; it returns Ok(Committed) describing the event plus the code-owned effects
the engine will apply, or Reject(reason). US1 covers CHANCE/GOAL/OWN_GOAL/FOUL/NOTHING;
substitutions, cards, and injuries are added in US2 (T024/T025).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..models import EventType, MatchPeriod, MatchState, Side, other_side
from .provider import ProposedEvent

# Types US1's validator understands. Others (YELLOW/RED/INJURY/SUBSTITUTION) are rejected
# until US2 extends this contract.
_US1_ACTION_TYPES = frozenset({
    EventType.CHANCE, EventType.GOAL, EventType.OWN_GOAL, EventType.FOUL, EventType.NOTHING,
})


@dataclass
class Committed:
    """A validated event plus the code-owned effects the engine applies on commit."""
    type: EventType
    team_side: Optional[Side]
    actor_id: Optional[str]
    secondary_id: Optional[str]
    commentary: str
    score_side: Optional[Side] = None          # regulation score to increment
    shootout_side: Optional[Side] = None        # shootout tally to increment (US3)
    advance_period: Optional[MatchPeriod] = None  # period transition (US3)
    ends_match: bool = False


@dataclass
class Ok:
    value: Committed


@dataclass
class Reject:
    reason: str


Result = Ok | Reject


def validate(proposed: ProposedEvent, state: MatchState) -> Result:
    etype = proposed.type
    if not isinstance(etype, EventType):
        return Reject(f"unknown event type {etype!r}")
    if etype not in _US1_ACTION_TYPES:
        return Reject(f"event type {etype.value} not supported yet")
    if etype == EventType.NOTHING:
        return Ok(Committed(EventType.NOTHING, None, None, None, proposed.commentary))

    side = proposed.team_side
    actor = proposed.actor_id
    if side not in ("home", "away"):
        return Reject(f"{etype.value} requires a team_side")
    if actor is None or actor not in state.players:
        return Reject(f"{etype.value} requires a known actor_id (got {actor!r})")

    if etype == EventType.OWN_GOAL:
        return _own_goal(proposed, state, side, actor)

    # Generic actor legality: actor belongs to team_side and is on the pitch.
    if state.side_of.get(actor) != side:
        return Reject(f"actor {actor} is not on team {side}")
    if not state.is_on_pitch(actor):
        return Reject(f"actor {actor} is not on the pitch")

    if etype == EventType.GOAL:
        return _goal(proposed, state, side, actor)
    if etype == EventType.FOUL:
        return _foul(proposed, state, side, actor)
    # CHANCE — narrative, no counters.
    return Ok(Committed(EventType.CHANCE, side, actor, None, proposed.commentary))


def _own_goal(proposed: ProposedEvent, state: MatchState, side: Side, actor: str) -> Result:
    if proposed.secondary_id is not None:
        return Reject("OWN_GOAL cannot carry an assist (secondary_id must be null)")
    if state.side_of.get(actor) != other_side(side):
        return Reject("OWN_GOAL actor must belong to the side opposite team_side")
    if not state.is_on_pitch(actor):
        return Reject(f"actor {actor} is not on the pitch")
    return Ok(Committed(EventType.OWN_GOAL, side, actor, None, proposed.commentary,
                        score_side=side))


def _goal(proposed: ProposedEvent, state: MatchState, side: Side, actor: str) -> Result:
    assist = proposed.secondary_id
    if assist is not None:
        if assist == actor or state.side_of.get(assist) != side or not state.is_on_pitch(assist):
            return Reject(f"invalid assist {assist!r}")
    return Ok(Committed(EventType.GOAL, side, actor, assist, proposed.commentary,
                        score_side=side))


def _foul(proposed: ProposedEvent, state: MatchState, side: Side, actor: str) -> Result:
    fouled = proposed.secondary_id
    if fouled is not None:
        if state.side_of.get(fouled) != other_side(side) or not state.is_on_pitch(fouled):
            return Reject("fouled player must be on the opposite side and on the pitch")
    return Ok(Committed(EventType.FOUL, side, actor, fouled, proposed.commentary))
