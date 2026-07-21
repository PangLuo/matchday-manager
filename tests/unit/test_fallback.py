"""T012 [US1]: fallback resolver legality invariants."""
import random

from matchday.match.fallback import resolve
from matchday.match.validate import Ok, validate
from matchday.models import EventType
from tests.support import build_state


def test_fallback_always_returns_a_legal_event():
    state = build_state()
    rng = random.Random(0)
    for _ in range(400):
        c = resolve(state, rng)
        # An actor, if present, must be on the pitch for its side.
        if c.actor_id is not None:
            assert state.is_on_pitch(c.actor_id)
            if c.type != EventType.OWN_GOAL:
                assert state.side_of[c.actor_id] == c.team_side


def test_fallback_can_produce_nothing():
    state = build_state()
    rng = random.Random(1)
    types = {resolve(state, rng).type for _ in range(400)}
    assert EventType.NOTHING in types


def test_fallback_is_seed_reproducible():
    state = build_state()
    a = [resolve(state, random.Random(42)).type for _ in range(10)]
    b = [resolve(state, random.Random(42)).type for _ in range(10)]
    assert a == b


def test_fallback_output_passes_the_validator():
    """The fallback is bound by the same rules the validator enforces."""
    from matchday.match.provider import ProposedEvent

    state = build_state()
    rng = random.Random(7)
    for _ in range(200):
        c = resolve(state, rng)
        proposed = ProposedEvent(c.type, c.team_side, c.actor_id, c.secondary_id, c.commentary)
        assert isinstance(validate(proposed, state), Ok)


def test_fallback_never_picks_off_pitch_actor_when_side_depleted():
    # away side has only one on-pitch player; fallback must still be legal.
    state = build_state(away_ids=["a1"])
    rng = random.Random(3)
    for _ in range(200):
        c = resolve(state, rng)
        if c.actor_id is not None:
            assert state.is_on_pitch(c.actor_id)
