"""Terminal play loop (T020; FR-001/002/004/005, US1 slice).

`python -m matchday.cli --new [--team ENG]` starts a new game, shows the squad, takes a
formation + XI + bench (interactive, or auto-picked with --auto), and plays the managed
team's first match moment-by-moment to a final score and report.

The real ClaudeProvider is wired here only (research R6). If the anthropic SDK or an API
key is unavailable, the game degrades to the deterministic fallback engine so a match still
completes (constitution 4) — the CLI announces this.
"""
from __future__ import annotations

import argparse
import random
import sys
from typing import Optional

from .formations import DEFAULT_FORMATION, formation_names
from .lineup import auto_lineup, validate_lineup
from .match.engine import build_match_state, build_report, simulate_match
from .match.prompt import PROMPT_VERSION
from .match.provider import ProviderError
from .models import AvailabilityStatus, Match, Team, Tournament
from .persistence import new_game


class _FallbackOnlyProvider:
    """Stand-in when no live model is available: forces the engine onto its fallback."""

    def propose(self, state, prompt_version):
        return ProviderError("no model configured")


def _make_provider(offline: bool):
    if offline:
        return _FallbackOnlyProvider(), True
    try:
        from .match.provider import ClaudeProvider
        return ClaudeProvider(), False
    except Exception as exc:  # noqa: BLE001 — missing SDK/key → degrade, don't crash
        print(f"[!] Live match engine unavailable ({exc}). "
              f"Playing on the offline fallback engine.\n")
        return _FallbackOnlyProvider(), True


def choose_team(tournament: Tournament, team_id: Optional[str], rng: random.Random) -> Team:
    if team_id:
        return tournament.team(team_id.upper())
    # Assign one at random when not chosen (FR-001).
    return tournament.team(rng.choice(sorted(tournament.teams)))


def display_squad(team: Team, availability: dict[str, AvailabilityStatus]) -> None:
    print(f"\n=== {team.name} squad ===")
    for pos in ("GK", "DEF", "MID", "FWD"):
        group = [p for p in team.players if p.position.value == pos]
        print(f"\n{pos}:")
        for p in sorted(group, key=lambda x: x.rating, reverse=True):
            status = availability.get(p.id)
            tag = "available" if status is None or status.is_available() else status.state.value
            print(f"  [{p.id}] {p.name:<22} rat={p.rating}  {tag}")


def find_first_fixture(tournament: Tournament, team_id: str) -> Match:
    for m in sorted(tournament.fixtures, key=lambda x: (x.matchday, x.id)):
        if team_id in (m.home_team, m.away_team):
            return m
    raise LookupError(f"no fixture found for {team_id}")


def _play(state, provider, home_name, away_name, offline, interactive) -> None:
    print(f"\nKICK-OFF: {home_name} vs {away_name}\n")

    def on_event(ev):
        who = state.players[ev.actor_id].name if ev.actor_id else ""
        line = f"{ev.minute:>3}'  {ev.type.value:<13} {who}"
        if ev.commentary:
            line += f" — {ev.commentary}"
        print(line)
        if interactive and ev.type.value not in ("FINAL_WHISTLE",):
            try:
                input()
            except EOFError:
                pass

    outcome = simulate_match(
        state, provider,
        prompt_version=PROMPT_VERSION,
        fallback_rng=random.Random(),
        on_event=on_event,
    )
    print("\n" + build_report(outcome, home_name, away_name, state.players))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="matchday", description="World Cup 2026 Team Manager")
    parser.add_argument("--new", action="store_true", help="start a new game")
    parser.add_argument("--team", help="team id to manage, e.g. ENG (random if omitted)")
    parser.add_argument("--formation", default=DEFAULT_FORMATION,
                        choices=formation_names(), help="starting formation")
    parser.add_argument("--auto", action="store_true",
                        help="auto-pick the lineup and play without prompts")
    parser.add_argument("--offline", action="store_true",
                        help="force the offline fallback engine (no API calls)")
    args = parser.parse_args(argv)

    if not args.new:
        parser.error("only --new is supported in this build (US1). Try: --new --team ENG")

    rng = random.Random()
    tournament = new_game()
    team = choose_team(tournament, args.team, rng)
    tournament.managed_team_id = team.id
    print(f"You are managing {team.name}.")
    display_squad(team, tournament.players_availability)

    # Build and validate the managed lineup (auto for this US1 slice; interactive TODO US2).
    lineup = auto_lineup(team, tournament.players_availability, args.formation)
    errors = validate_lineup(lineup, tournament.players_availability)
    if errors:
        print("\nLineup rejected:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"\nLineup accepted ({lineup.formation.name}): "
          + ", ".join(p.name for p in lineup.starters))

    fixture = find_first_fixture(tournament, team.id)
    opp_id = fixture.away_team if fixture.home_team == team.id else fixture.home_team
    opp = tournament.team(opp_id)
    opp_lineup = auto_lineup(opp, tournament.players_availability, DEFAULT_FORMATION)

    if fixture.home_team == team.id:
        home_lineup, away_lineup, home, away = lineup, opp_lineup, team, opp
    else:
        home_lineup, away_lineup, home, away = opp_lineup, lineup, opp, team

    state = build_match_state(home_lineup, away_lineup, home.id, away.id, fixture.phase)
    provider, offline = _make_provider(args.offline)
    _play(state, provider, home.name, away.name, offline, interactive=not args.auto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
