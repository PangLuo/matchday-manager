"""T010 [US1]: lineup validation (FR-004/005/006)."""
from matchday.formations import get_formation
from matchday.lineup import validate_lineup
from matchday.models import (
    AvailabilityState,
    AvailabilityStatus,
    Lineup,
    Player,
    Position,
)

GK, DEF, MID, FWD = Position.GK, Position.DEF, Position.MID, Position.FWD


def _squad():
    players = []
    counts = {GK: 3, DEF: 8, MID: 8, FWD: 7}
    for pos, n in counts.items():
        for i in range(n):
            pid = f"{pos.value}{i}"
            players.append(Player(id=pid, name=pid, position=pos))
    return {p.id: p for p in players}


def _avail(ids, unavailable=None):
    unavailable = unavailable or {}
    table = {pid: AvailabilityStatus() for pid in ids}
    for pid, state in unavailable.items():
        table[pid] = AvailabilityStatus(state=state, matches_remaining=1)
    return table


def _lineup_433(squad, formation="4-3-3"):
    frm = get_formation(formation)
    by_pos = {pos: [p for p in squad.values() if p.position == pos] for pos in Position}
    picks, cursor = [], {pos: 0 for pos in Position}
    for slot in frm.slots:
        picks.append(by_pos[slot][cursor[slot]])
        cursor[slot] += 1
    bench = [p for p in squad.values() if p not in picks][:7]
    return Lineup(formation=frm, starters=picks, bench=bench)


def test_valid_lineup_has_no_errors():
    squad = _squad()
    lineup = _lineup_433(squad)
    errors = validate_lineup(lineup, _avail(squad))
    assert errors == []


def test_wrong_starter_count_rejected():
    squad = _squad()
    lineup = _lineup_433(squad)
    lineup.starters = lineup.starters[:10]
    errors = validate_lineup(lineup, _avail(squad))
    assert any("11" in e for e in errors)


def test_formation_shape_mismatch_rejected():
    squad = _squad()
    lineup = _lineup_433(squad)
    # Swap a forward slot for an extra defender → shape no longer matches 4-3-3.
    extra_def = next(p for p in squad.values()
                     if p.position == Position.DEF and p not in lineup.starters)
    lineup.starters[-1] = extra_def
    errors = validate_lineup(lineup, _avail(squad))
    assert any("formation" in e.lower() for e in errors)


def test_unavailable_player_rejected():
    squad = _squad()
    lineup = _lineup_433(squad)
    injured = lineup.starters[5].id
    errors = validate_lineup(
        lineup, _avail(squad, {injured: AvailabilityState.INJURED})
    )
    assert any("not available" in e.lower() for e in errors)


def test_duplicate_player_rejected():
    squad = _squad()
    lineup = _lineup_433(squad)
    lineup.bench[0] = lineup.starters[0]
    errors = validate_lineup(lineup, _avail(squad))
    assert any("once" in e.lower() for e in errors)
