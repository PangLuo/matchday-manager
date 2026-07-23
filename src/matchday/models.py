"""Core domain types: enums and dataclasses (data-model.md).

Explicit data, no ORM (constitution: minimal). Availability is NOT stored on Player — it
lives in the tournament's `players_availability` table, the single source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional

Side = Literal["home", "away"]
SIDES: tuple[Side, Side] = ("home", "away")


def other_side(side: Side) -> Side:
    return "away" if side == "home" else "home"


class Position(str, Enum):
    GK = "GK"
    DEF = "DEF"
    MID = "MID"
    FWD = "FWD"


class Phase(str, Enum):
    GROUP = "GROUP"
    R32 = "R32"
    R16 = "R16"
    QF = "QF"
    SF = "SF"
    THIRD_PLACE = "THIRD_PLACE"
    FINAL = "FINAL"
    DONE = "DONE"


class AvailabilityState(str, Enum):
    AVAILABLE = "AVAILABLE"
    INJURED = "INJURED"
    SUSPENDED = "SUSPENDED"


class EventType(str, Enum):
    KICKOFF = "KICKOFF"
    CHANCE = "CHANCE"
    GOAL = "GOAL"
    OWN_GOAL = "OWN_GOAL"
    FOUL = "FOUL"
    YELLOW = "YELLOW"
    RED = "RED"
    INJURY = "INJURY"
    SUBSTITUTION = "SUBSTITUTION"
    HALF_TIME = "HALF_TIME"
    FULL_TIME = "FULL_TIME"
    EXTRA_TIME = "EXTRA_TIME"
    PENALTY_SHOOTOUT = "PENALTY_SHOOTOUT"
    FINAL_WHISTLE = "FINAL_WHISTLE"
    NOTHING = "NOTHING"


#: Markers that carry no actor and are legal purely as clock/phase transitions.
PERIOD_MARKERS = frozenset({
    EventType.KICKOFF, EventType.HALF_TIME, EventType.FULL_TIME,
    EventType.EXTRA_TIME, EventType.PENALTY_SHOOTOUT, EventType.FINAL_WHISTLE,
})


class EventSource(str, Enum):
    MODEL = "MODEL"
    FALLBACK = "FALLBACK"


class MatchPeriod(str, Enum):
    REGULATION = "REGULATION"
    EXTRA_TIME = "EXTRA_TIME"
    SHOOTOUT = "SHOOTOUT"


@dataclass
class Player:
    id: str
    name: str
    position: Position
    rating: int = 60
    attack: int = 50
    defense: int = 50
    discipline: int = 65
    injury_proneness: int = 30
    emergency_callup: bool = False


@dataclass
class AvailabilityStatus:
    state: AvailabilityState = AvailabilityState.AVAILABLE
    matches_remaining: int = 0
    accumulated_yellows: int = 0

    def is_available(self) -> bool:
        return self.state == AvailabilityState.AVAILABLE

    def validate(self) -> None:
        if self.matches_remaining < 0:
            raise ValueError("matches_remaining must be >= 0")
        if self.state != AvailabilityState.AVAILABLE and self.matches_remaining < 1:
            raise ValueError(f"{self.state} requires matches_remaining >= 1")


@dataclass
class Team:
    id: str
    name: str
    group_id: str
    fifa_ranking: int
    conduct_points: int = 0
    players: list[Player] = field(default_factory=list)

    def player(self, player_id: str) -> Player:
        for p in self.players:
            if p.id == player_id:
                return p
        raise KeyError(player_id)


@dataclass
class Formation:
    name: str
    slots: list[Position]


@dataclass
class Lineup:
    formation: Formation
    starters: list[Player]
    bench: list[Player]


@dataclass
class MatchEvent:
    moment_index: int
    minute: int
    type: EventType
    commentary: str
    team_side: Optional[Side] = None
    actor_id: Optional[str] = None
    secondary_id: Optional[str] = None
    period: MatchPeriod = MatchPeriod.REGULATION
    source: EventSource = EventSource.MODEL


@dataclass
class Substitution:
    moment_index: int
    team_side: Side
    player_out: str
    player_in: str


@dataclass
class MatchResult:
    home: int
    away: int
    winner: Optional[Side] = None          # None for a drawn group match
    decided_by: str = "normal"             # normal | extra_time | penalties


@dataclass
class Match:
    id: str
    phase: Phase
    home_team: str
    away_team: str
    matchday: int
    group_id: Optional[str] = None
    events: list[MatchEvent] = field(default_factory=list)
    result: Optional[MatchResult] = None


@dataclass
class Group:
    id: str
    team_ids: list[str]
    standings: Optional[list[str]] = None   # resolved order, computed once & stored (US3)


@dataclass
class Tournament:
    managed_team_id: Optional[str]
    phase: Phase
    teams: dict[str, Team]
    groups: list[Group]
    fixtures: list[Match]
    bracket: list[Match] = field(default_factory=list)
    players_availability: dict[str, AvailabilityStatus] = field(default_factory=dict)
    prompt_version: str = "v1"

    def team(self, team_id: str) -> Team:
        return self.teams[team_id]

    def availability(self, player_id: str) -> AvailabilityStatus:
        return self.players_availability.setdefault(player_id, AvailabilityStatus())


# --------------------------------------------------------------------------------------
# Live match simulation state (managed matches). Distinct from the persisted `Match`
# record: this is the mutable working state the engine/validate/fallback operate on.
# --------------------------------------------------------------------------------------
@dataclass
class MatchState:
    home_team_id: str
    away_team_id: str
    phase: Phase
    players: dict[str, Player]                       # both squads, by id (attributes)
    side_of: dict[str, Side]                          # player_id -> side
    on_pitch: dict[Side, set[str]]                    # currently on the pitch
    bench: dict[Side, set[str]]                       # eligible, not yet used
    used: dict[Side, set[str]]                        # every id that has left or entered
    subs_used: dict[Side, int]
    yellows: dict[str, int] = field(default_factory=dict)   # in-match yellow counts
    sent_off: set[str] = field(default_factory=set)
    injured_off: set[str] = field(default_factory=set)
    score: dict[Side, int] = field(default_factory=lambda: {"home": 0, "away": 0})
    shootout: dict[Side, int] = field(default_factory=lambda: {"home": 0, "away": 0})
    current_period: MatchPeriod = MatchPeriod.REGULATION
    extra_time_reached: bool = False
    minute: int = 0
    moment_index: int = 0
    luck: float = 0.0                                       # code-supplied per-moment nudge
    history: list["MatchEvent"] = field(default_factory=list)  # committed events so far

    def sub_limit(self, side: Side) -> int:
        return 6 if self.extra_time_reached else 5

    def is_on_pitch(self, player_id: str) -> bool:
        side = self.side_of.get(player_id)
        return side is not None and player_id in self.on_pitch[side]

    def on_pitch_count(self, side: Side) -> int:
        return len(self.on_pitch[side])
