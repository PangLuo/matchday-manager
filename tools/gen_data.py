"""Deterministic generator for the bundled static tournament data (T003-T005).

Emits src/matchday/data/{teams,groups,squads,fixtures}.json.

IMPORTANT — data honesty: the 48 team names, 12-group structure, and FIFA-ranking
ordering are a *plausible* representation of a 48-team World Cup, NOT a guaranteed match
for the real 2026 draw. Player names and attributes are **synthetic, deterministically
generated placeholders** — they are not real footballers. The game logic only relies on
structural properties (26 players, >=3 GK per squad, attributes in range), per spec
Assumptions (ratings/attributes are data-driven and unspecified).

Run:  python tools/gen_data.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "matchday" / "data"
SEED = 2026

# 48 teams (code, name), ordered roughly by strength → gives fifa_ranking 1..48.
TEAMS = [
    ("ARG", "Argentina"), ("FRA", "France"), ("ESP", "Spain"), ("ENG", "England"),
    ("BRA", "Brazil"), ("POR", "Portugal"), ("NED", "Netherlands"), ("BEL", "Belgium"),
    ("ITA", "Italy"), ("GER", "Germany"), ("CRO", "Croatia"), ("URU", "Uruguay"),
    ("COL", "Colombia"), ("MAR", "Morocco"), ("USA", "United States"), ("MEX", "Mexico"),
    ("SUI", "Switzerland"), ("JPN", "Japan"), ("SEN", "Senegal"), ("DEN", "Denmark"),
    ("IRN", "Iran"), ("KOR", "South Korea"), ("AUS", "Australia"), ("ECU", "Ecuador"),
    ("AUT", "Austria"), ("UKR", "Ukraine"), ("SWE", "Sweden"), ("WAL", "Wales"),
    ("POL", "Poland"), ("SRB", "Serbia"), ("EGY", "Egypt"), ("NGA", "Nigeria"),
    ("CAN", "Canada"), ("PER", "Peru"), ("CHI", "Chile"), ("TUN", "Tunisia"),
    ("CMR", "Cameroon"), ("GHA", "Ghana"), ("CIV", "Ivory Coast"), ("QAT", "Qatar"),
    ("KSA", "Saudi Arabia"), ("CRC", "Costa Rica"), ("PAN", "Panama"), ("JAM", "Jamaica"),
    ("NOR", "Norway"), ("TUR", "Turkey"), ("GRE", "Greece"), ("NZL", "New Zealand"),
]
GROUP_IDS = [chr(ord("A") + i) for i in range(12)]  # A..L

FIRST_NAMES = [
    "Liam", "Mateo", "Noah", "Lucas", "Leon", "Hugo", "Adam", "Louis", "Gabriel", "Ali",
    "Yusuf", "Diego", "Marco", "Andre", "Ivan", "Nikola", "Kenji", "Min-jun", "Omar",
    "Samuel", "Thomas", "Daniel", "David", "Victor", "Bruno", "Pedro", "Kylian", "Sergio",
    "Aaron", "Felix", "Oscar", "Emre", "Kai", "Rasmus", "Milan", "Luka", "Youssef", "Carlos",
    "Mohammed", "Jung-woo", "Takumi", "Santiago", "Federico", "Mario", "Erik", "Jonas",
]
LAST_NAMES = [
    "Silva", "Muller", "Kim", "Tanaka", "Rossi", "Dubois", "Kovac", "Novak", "Andersen",
    "Hansen", "Okafor", "Diallo", "Traore", "Mendez", "Garcia", "Fernandez", "Lopez",
    "Costa", "Santos", "Bianchi", "Weber", "Schneider", "Petrov", "Ivanov", "Nakamura",
    "Park", "Haddad", "Nasser", "Bergman", "Larsen", "Moreau", "Bernard", "Horvat",
    "Maric", "Adebayo", "Osei", "Vargas", "Rojas", "Castillo", "Ferrari", "Popovic",
    "Yilmaz", "Demir", "Nielsen", "Johansson", "Virtanen", "Abbas", "Salah",
]

# Per-squad position template: 3 GK, 8 DEF, 8 MID, 7 FWD = 26 (>=3 GK guaranteed).
SQUAD_TEMPLATE = ["GK"] * 3 + ["DEF"] * 8 + ["MID"] * 8 + ["FWD"] * 7


def clamp(v: int, lo: int = 1, hi: int = 99) -> int:
    return max(lo, min(hi, v))


def gen_squad(rng: random.Random, code: str, base: int) -> list[dict]:
    """26 players for a team whose average rating tracks `base` (stronger team → higher)."""
    used_names: set[str] = set()
    players = []
    for i, pos in enumerate(SQUAD_TEMPLATE, start=1):
        while True:
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            if name not in used_names:
                used_names.add(name)
                break
        rating = clamp(int(rng.gauss(base, 6)))
        # Attribute bias by position; all still data-only signals for prompt/fallback.
        if pos == "GK":
            attack, defense = clamp(rating - 40), clamp(rating + 2)
        elif pos == "DEF":
            attack, defense = clamp(rating - 20), clamp(rating + 6)
        elif pos == "MID":
            attack, defense = clamp(rating), clamp(rating - 2)
        else:  # FWD
            attack, defense = clamp(rating + 6), clamp(rating - 20)
        players.append({
            "id": f"p_{code}_{i:02d}",
            "name": name,
            "position": pos,
            "rating": rating,
            "attack": attack,
            "defense": defense,
            "discipline": clamp(int(rng.gauss(65, 15))),
            "injury_proneness": clamp(int(rng.gauss(30, 15))),
        })
    return players


def round_robin(team_ids: list[str]) -> list[tuple[int, tuple[str, str]]]:
    """4-team single round-robin → 6 pairings over 3 matchdays. Returns (matchday, (home, away))."""
    a, b, c, d = team_ids
    return [
        (1, (a, b)), (1, (c, d)),
        (2, (a, c)), (2, (d, b)),
        (3, (a, d)), (3, (b, c)),
    ]


def build_knockout_template() -> list[dict]:
    """32-match knockout template with slot tokens; seeding logic lives in tournament.py (US3).

    R32 slots reference group finishers ("1A" = winner of group A, "2B" = runner-up of B,
    "3X" = a best-third placeholder resolved at seeding). R16+ reference prior winners
    ("W:k_R32_01"). Concrete pairings are filled when the group stage completes.
    """
    matches: list[dict] = []

    # R32: 16 matches. Home/away slot tokens are structural placeholders (seeded in US3).
    r32_slots = [
        ("1A", "3CDF"), ("1C", "3ABF"), ("1E", "3ABCD"), ("1G", "3BEFJ"),
        ("1I", "3EHIJ"), ("1K", "3DEIL"), ("2A", "2C"), ("2E", "2G"),
        ("1B", "3AEFG"), ("1D", "3BEHL"), ("1F", "2H"), ("1H", "2F"),
        ("1J", "3BCEH"), ("1L", "2J"), ("2B", "2D"), ("2I", "2L"),
    ]
    for n, (home, away) in enumerate(r32_slots, start=1):
        matches.append({
            "id": f"k_R32_{n:02d}", "phase": "R32", "matchday": 4,
            "home_slot": home, "away_slot": away,
        })

    def pair_up(prev_phase: str, phase: str, matchday: int, start_n: int) -> None:
        prev = [m["id"] for m in matches if m["phase"] == prev_phase]
        for n, (h, a) in enumerate(zip(prev[0::2], prev[1::2]), start=1):
            matches.append({
                "id": f"k_{phase}_{n:02d}", "phase": phase, "matchday": matchday,
                "home_slot": f"W:{h}", "away_slot": f"W:{a}",
            })

    pair_up("R32", "R16", 5, 1)   # 8
    pair_up("R16", "QF", 6, 1)    # 4
    pair_up("QF", "SF", 7, 1)     # 2

    sf = [m["id"] for m in matches if m["phase"] == "SF"]
    matches.append({
        "id": "k_3RD_01", "phase": "THIRD_PLACE", "matchday": 8,
        "home_slot": f"L:{sf[0]}", "away_slot": f"L:{sf[1]}",
    })
    matches.append({
        "id": "k_FINAL_01", "phase": "FINAL", "matchday": 8,
        "home_slot": f"W:{sf[0]}", "away_slot": f"W:{sf[1]}",
    })
    return matches


def main() -> None:
    rng = random.Random(SEED)

    teams, groups_map = [], {g: [] for g in GROUP_IDS}
    for idx, (code, name) in enumerate(TEAMS):
        group_id = GROUP_IDS[idx % 12]
        teams.append({
            "id": code, "name": name, "group_id": group_id, "fifa_ranking": idx + 1,
        })
        groups_map[group_id].append(code)

    groups = [{"id": g, "team_ids": groups_map[g]} for g in GROUP_IDS]

    squads = {}
    for t in teams:
        # Stronger teams (low ranking) get a higher base rating (~78 down to ~62).
        base = int(78 - (t["fifa_ranking"] - 1) * (16 / 47))
        squads[t["id"]] = gen_squad(rng, t["id"], base)

    group_stage = []
    for g in groups:
        for matchday, (home, away) in round_robin(g["team_ids"]):
            group_stage.append({
                "id": f"m_{g['id']}_{matchday}_{home}", "phase": "GROUP",
                "group_id": g["id"], "matchday": matchday, "home": home, "away": away,
            })

    fixtures = {"group_stage": group_stage, "knockout": build_knockout_template()}

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write(DATA_DIR / "teams.json", teams)
    _write(DATA_DIR / "groups.json", groups)
    _write(DATA_DIR / "squads.json", squads)
    _write(DATA_DIR / "fixtures.json", fixtures)

    total_players = sum(len(v) for v in squads.values())
    print(f"teams={len(teams)} groups={len(groups)} players={total_players} "
          f"group_matches={len(group_stage)} knockout={len(fixtures['knockout'])} "
          f"total_fixtures={len(group_stage) + len(fixtures['knockout'])}")


def _write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
