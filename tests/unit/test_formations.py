"""T009 [US1]: formation menu shape rules."""
from matchday.formations import FORMATIONS, formation_names, get_formation
from matchday.models import Position


def test_every_formation_has_exactly_11_slots():
    for name, frm in FORMATIONS.items():
        assert len(frm.slots) == 11, f"{name} has {len(frm.slots)} slots"


def test_every_formation_has_exactly_one_goalkeeper():
    for name, frm in FORMATIONS.items():
        gk = sum(1 for s in frm.slots if s == Position.GK)
        assert gk == 1, f"{name} has {gk} GK slots"


def test_menu_is_non_empty_and_named():
    assert formation_names(), "formation menu is empty"
    for name in formation_names():
        assert get_formation(name).name == name


def test_unknown_formation_raises():
    import pytest

    with pytest.raises(KeyError):
        get_formation("6-0-4")
