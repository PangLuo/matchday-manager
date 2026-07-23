"""Versioned prompt construction (T014).

Cross-replay variety (FR-009) comes from fresh unseeded sampling at MATCH_TEMPERATURE,
plus a code-supplied per-moment "luck" nudge (research R2) — never from a high temperature.
"""
from __future__ import annotations

from ..models import MatchState, other_side

#: Bump when the prompt changes so logs/saves remain interpretable (constitution 5).
#: v2 — feed full match history and wire the per-moment luck nudge (was dead in v1).
PROMPT_VERSION = "v2"

#: Low (grounded commentary) but non-zero, so fresh sampling still varies streams (FR-009).
MATCH_TEMPERATURE = 0.4

#: The event types the model MAY propose. Period markers are code-emitted, never proposed;
#: cards/injuries/substitutions arrive in US2.
_PROPOSABLE_TYPES = ["CHANCE", "GOAL", "OWN_GOAL", "FOUL", "NOTHING"]

PROPOSED_EVENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "type": {"type": "string", "enum": _PROPOSABLE_TYPES},
        "team_side": {"anyOf": [{"type": "string", "enum": ["home", "away"]}, {"type": "null"}]},
        "actor_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "secondary_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "commentary": {"type": "string"},
    },
    "required": ["type", "team_side", "actor_id", "secondary_id", "commentary"],
}


def build_system() -> str:
    return (
        "You are the match engine for a football simulation. Each turn you decide what "
        "happens in the next discrete moment of the match and return ONE structured event. "
        "Reason over the on-pitch players' numeric attributes, the scoreline, the minute, "
        "the match-so-far history, and the supplied luck nudge.\n"
        "The luck nudge is a signed value in [-1, 1] for THIS moment: strongly positive "
        "favours a decisive attacking outcome (a GOAL or clear CHANCE) for the HOME side, "
        "strongly negative favours one for the AWAY side, and near zero favours a quiet or "
        "uneventful moment (NOTHING, a FOUL, a half-chance). Weigh it together with player "
        "attributes — a big nudge toward a strong attacker should often become a GOAL.\n"
        "Do NOT simply repeat the previous moment's action, actor, or phrasing: let the "
        "match evolve — vary who is involved and what unfolds, and reflect the running "
        "score and momentum. Keep commentary to one or two grounded sentences. Only "
        "reference players currently on the pitch. Never set the score, cards, or "
        "substitution counters — those are computed by code."
    )


def _roster(state: MatchState, side) -> str:
    lines = []
    for pid in sorted(state.on_pitch[side]):
        p = state.players[pid]
        lines.append(
            f"  {p.id} {p.name} ({p.position.value}) "
            f"atk={p.attack} def={p.defense} rat={p.rating}"
        )
    return "\n".join(lines)


def _history(state: MatchState) -> str:
    if not state.history:
        return "  (kick-off imminent — nothing has happened yet)"
    lines = []
    for ev in state.history:
        who = state.players[ev.actor_id].name if ev.actor_id in state.players else ""
        line = f"  {ev.minute:>3}' {ev.type.value}"
        if who:
            line += f" {who}"
        if ev.commentary:
            line += f" — {ev.commentary}"
        lines.append(line)
    return "\n".join(lines)


def build_user(state: MatchState) -> str:
    home, away = "home", other_side("home")
    return (
        f"Minute {state.minute}. Score home {state.score['home']} - "
        f"{state.score['away']} away. Luck nudge: {state.luck:+.2f}.\n"
        f"HOME on pitch:\n{_roster(state, home)}\n"
        f"AWAY on pitch:\n{_roster(state, away)}\n"
        f"Match so far:\n{_history(state)}\n"
        "Decide the next moment — advancing the story rather than repeating it."
    )


def build_messages(state: MatchState) -> list[dict]:
    return [{"role": "user", "content": build_user(state)}]
