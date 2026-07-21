"""T021 [US1]: a full managed match via FakeProvider — no network (quickstart V1/V6).

Asserts rule adherence and structure only, never a specific score (constitution 3).
US2 extends this file with substitution/card/injury scenarios (T023).
"""
import random

from matchday.lineup import auto_lineup
from matchday.match.engine import build_match_state, simulate_match
from matchday.match.provider import FakeProvider, ProposedEvent, ProviderError
from matchday.models import EventSource, EventType
from matchday.persistence import new_game


def _match_state():
    t = new_game("ENG")
    eng, bra = t.team("ENG"), t.team("BRA")
    home = auto_lineup(eng, t.players_availability, "4-3-3")
    away = auto_lineup(bra, t.players_availability, "4-4-2")
    return build_match_state(home, away, "ENG", "BRA")


def _home_scorer(state):
    actor = sorted(state.on_pitch["home"])[9]
    return ProposedEvent(EventType.GOAL, "home", actor, None, "Home goal!")


def _own_goal_by_away(state):
    actor = sorted(state.on_pitch["away"])[1]  # an away defender
    return ProposedEvent(EventType.OWN_GOAL, "home", actor, None, "Unlucky own goal!")


def _home_chance(state):
    return ProposedEvent(EventType.CHANCE, "home", sorted(state.on_pitch["home"])[8], None, "Close!")


def test_full_match_reaches_final_whistle_with_legal_events():
    state = _match_state()
    script = [
        _home_chance,
        _home_scorer,
        _own_goal_by_away,
        # A provider-error burst (3 = MAX_RETRIES+1) forces one moment to the fallback.
        ProviderError("timeout"), ProviderError("timeout"), ProviderError("timeout"),
    ]
    outcome = simulate_match(
        state, FakeProvider(script),
        prompt_version="v1", fallback_rng=random.Random(123),
    )

    assert outcome.events[0].type == EventType.KICKOFF
    assert outcome.events[-1].type == EventType.FINAL_WHISTLE
    assert any(e.type == EventType.HALF_TIME for e in outcome.events)
    assert any(e.type == EventType.FULL_TIME for e in outcome.events)

    # Degradation surfaced: the error burst produced at least one FALLBACK event.
    assert outcome.degraded
    assert any(e.source == EventSource.FALLBACK for e in outcome.events)

    # Every actor named in an event was on the pitch for the relevant side.
    for e in outcome.events:
        if e.actor_id is None:
            continue
        assert state.is_on_pitch(e.actor_id)
        if e.type == EventType.OWN_GOAL:
            assert state.side_of[e.actor_id] != e.team_side
        elif e.team_side is not None:
            assert state.side_of[e.actor_id] == e.team_side

    # Score-accumulation rule: result equals the goals credited to each side.
    home_goals = sum(1 for e in outcome.events
                     if (e.type == EventType.GOAL and e.team_side == "home")
                     or (e.type == EventType.OWN_GOAL and e.team_side == "home"))
    away_goals = sum(1 for e in outcome.events
                     if (e.type == EventType.GOAL and e.team_side == "away")
                     or (e.type == EventType.OWN_GOAL and e.team_side == "away"))
    assert outcome.result.home == home_goals
    assert outcome.result.away == away_goals


def test_match_runs_entirely_on_the_fallback_when_provider_is_down():
    """Quickstart V6: with every call failing, the match still reaches a valid result."""
    state = _match_state()

    class DownProvider:
        def propose(self, state, prompt_version):
            return ProviderError("model unavailable")

    outcome = simulate_match(state, DownProvider(), fallback_rng=random.Random(0))
    assert outcome.events[-1].type == EventType.FINAL_WHISTLE
    assert outcome.degraded
    assert all(
        e.source == EventSource.FALLBACK
        for e in outcome.events
        if e.type not in {EventType.KICKOFF, EventType.HALF_TIME,
                          EventType.FULL_TIME, EventType.FINAL_WHISTLE}
    )
