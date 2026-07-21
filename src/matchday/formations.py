"""The fixed menu of standard formations (FR-004; data-model Formation).

Each formation is exactly 11 positional slots including exactly one GK. Custom formations
are out of scope. Slot order is GK, then defenders, midfielders, forwards.
"""
from __future__ import annotations

from .models import Formation, Position

GK, DEF, MID, FWD = Position.GK, Position.DEF, Position.MID, Position.FWD


def _f(name: str, d: int, m: int, f: int) -> Formation:
    return Formation(name=name, slots=[GK] + [DEF] * d + [MID] * m + [FWD] * f)


#: The offered menu, keyed by name. Every entry has 1 GK + 10 outfield = 11 slots.
FORMATIONS: dict[str, Formation] = {
    frm.name: frm
    for frm in [
        _f("4-4-2", 4, 4, 2),
        _f("4-3-3", 4, 3, 3),
        _f("3-5-2", 3, 5, 2),
        _f("4-2-3-1", 4, 5, 1),
        _f("5-3-2", 5, 3, 2),
        _f("3-4-3", 3, 4, 3),
    ]
}

DEFAULT_FORMATION = "4-3-3"


def get_formation(name: str) -> Formation:
    if name not in FORMATIONS:
        raise KeyError(f"unknown formation {name!r}; choose one of {sorted(FORMATIONS)}")
    return FORMATIONS[name]


def formation_names() -> list[str]:
    return list(FORMATIONS)
