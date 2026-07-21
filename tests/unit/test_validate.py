"""T011 [US1]: core event validation + known-bad corpus #3, #7, #9, #11.

US2 extends this file with the substitution/card/injury corpus (T022).
"""
from matchday.match.provider import ProposedEvent
from matchday.match.validate import Ok, Reject, validate
from matchday.models import EventType
from tests.support import build_state


def _ok(proposed, state):
    result = validate(proposed, state)
    assert isinstance(result, Ok), getattr(result, "reason", result)
    return result.value


def _reject(proposed, state):
    result = validate(proposed, state)
    assert isinstance(result, Reject), f"expected Reject, got {result}"
    return result.reason


def test_goal_by_on_pitch_player_ok_and_scores():
    state = build_state()
    c = _ok(ProposedEvent(EventType.GOAL, "home", "h9", None, "Goal!"), state)
    assert c.score_side == "home"


def test_goal_with_valid_assist_ok():
    state = build_state()
    c = _ok(ProposedEvent(EventType.GOAL, "home", "h9", "h7", "Assisted goal!"), state)
    assert c.secondary_id == "h7"


def test_chance_and_foul_narrative_ok():
    state = build_state()
    _ok(ProposedEvent(EventType.CHANCE, "away", "a10", None, "A chance!"), state)
    _ok(ProposedEvent(EventType.FOUL, "home", "h4", "a10", "A foul."), state)


def test_nothing_is_legal():
    state = build_state()
    _ok(ProposedEvent(EventType.NOTHING, None, None, None, "Nothing doing."), state)


def test_own_goal_opposite_side_actor_ok():
    state = build_state()
    # team_side home scores; actor is an away defender.
    c = _ok(ProposedEvent(EventType.OWN_GOAL, "home", "a4", None, "Own goal!"), state)
    assert c.score_side == "home"


# --- known-bad corpus ---------------------------------------------------------
def test_kb3_actor_on_other_team_rejected():
    state = build_state()
    reason = _reject(ProposedEvent(EventType.GOAL, "home", "a9", None, "?"), state)
    assert "team" in reason.lower()


def test_kb7_goal_without_scorer_rejected():
    state = build_state()
    _reject(ProposedEvent(EventType.GOAL, "home", None, None, "?"), state)
    _reject(ProposedEvent(EventType.GOAL, "home", "ghost", None, "?"), state)


def test_kb9_type_outside_enum_rejected():
    state = build_state()
    bogus = ProposedEvent("TELEPORT", "home", "h9", None, "?")  # type: ignore[arg-type]
    _reject(bogus, state)


def test_kb11_own_goal_wrong_side_or_with_assist_rejected():
    state = build_state()
    # actor belongs to team_side itself → illegal.
    _reject(ProposedEvent(EventType.OWN_GOAL, "home", "h4", None, "?"), state)
    # own goal with a non-null assist → illegal.
    _reject(ProposedEvent(EventType.OWN_GOAL, "home", "a4", "a5", "?"), state)


def test_off_pitch_actor_rejected():
    state = build_state(home_ids=[f"h{i}" for i in range(1, 12)], home_bench=["h99"])
    # h99 is on the bench, not on the pitch → cannot act.
    _reject(ProposedEvent(EventType.GOAL, "home", "h99", None, "?"), state)
