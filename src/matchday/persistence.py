"""Persistence (T008 slice): load bundled static data into a fresh Tournament.

Full save/load of an in-progress run is T041 (US3). This module currently provides only
the new-game bootstrap: read the read-only bundled JSON and assemble an in-memory
Tournament with every player AVAILABLE, group-phase fixtures scheduled, and an empty
bracket.
"""
from __future__ import annotations

import json
from importlib import resources
from typing import Any

from .models import (
    AvailabilityStatus,
    Group,
    Match,
    Phase,
    Player,
    Position,
    Team,
    Tournament,
)


def _load_json(name: str) -> Any:
    """Read a bundled data file (works both installed and from a source checkout)."""
    with resources.files("matchday.data").joinpath(name).open(encoding="utf-8") as fh:
        return json.load(fh)


def load_teams_and_squads() -> dict[str, Team]:
    teams_raw = _load_json("teams.json")
    squads_raw = _load_json("squads.json")
    teams: dict[str, Team] = {}
    for t in teams_raw:
        squad = [
            Player(
                id=p["id"],
                name=p["name"],
                position=Position(p["position"]),
                rating=p["rating"],
                attack=p["attack"],
                defense=p["defense"],
                discipline=p["discipline"],
                injury_proneness=p["injury_proneness"],
            )
            for p in squads_raw[t["id"]]
        ]
        teams[t["id"]] = Team(
            id=t["id"],
            name=t["name"],
            group_id=t["group_id"],
            fifa_ranking=t["fifa_ranking"],
            players=squad,
        )
    return teams


def load_groups() -> list[Group]:
    return [Group(id=g["id"], team_ids=list(g["team_ids"])) for g in _load_json("groups.json")]


def load_group_fixtures() -> list[Match]:
    fixtures = _load_json("fixtures.json")
    return [
        Match(
            id=m["id"],
            phase=Phase.GROUP,
            home_team=m["home"],
            away_team=m["away"],
            matchday=m["matchday"],
            group_id=m["group_id"],
        )
        for m in fixtures["group_stage"]
    ]


def new_game(managed_team_id: str | None = None) -> Tournament:
    """Assemble a fresh Tournament from bundled data (all players AVAILABLE)."""
    teams = load_teams_and_squads()
    if managed_team_id is not None and managed_team_id not in teams:
        raise KeyError(f"unknown team id {managed_team_id!r}")

    availability = {
        player.id: AvailabilityStatus()
        for team in teams.values()
        for player in team.players
    }

    return Tournament(
        managed_team_id=managed_team_id,
        phase=Phase.GROUP,
        teams=teams,
        groups=load_groups(),
        fixtures=load_group_fixtures(),
        bracket=[],
        players_availability=availability,
        prompt_version="v1",
    )
