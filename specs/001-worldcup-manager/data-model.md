# Phase 1 Data Model: World Cup 2026 Team Manager

Entities as plain Python dataclasses (constitution: explicit data, no ORM). Fields are
described conceptually; types shown are indicative. Persisted shapes live in
`contracts/save-file-schema.md`.

## Enumerations

- **Position**: `GK | DEF | MID | FWD` (fine-grained slots resolved by the formation).
- **Phase**: `GROUP | R32 | R16 | QF | SF | THIRD_PLACE | FINAL | DONE`.
- **AvailabilityState**: `AVAILABLE | INJURED | SUSPENDED`.
- **EventType**: `KICKOFF | CHANCE | GOAL | OWN_GOAL | FOUL | YELLOW | RED | INJURY |
  SUBSTITUTION | HALF_TIME | FULL_TIME | EXTRA_TIME | PENALTY_SHOOTOUT | FINAL_WHISTLE |
  NOTHING`. `OWN_GOAL` mirrors `GOAL` (same score-increment-by-code effect for `team_side`)
  but `actor_id` is the defender on the **opposite** side.
- **EventSource**: `MODEL | FALLBACK` (provenance; drives the degradation surface).
- **MatchPeriod**: `REGULATION | EXTRA_TIME | SHOOTOUT`. The phase of play an event belongs
  to, **set by code** from the match's current phase (never by the model). Replay uses it to
  keep penalty-shootout kicks out of the regulation scoreline: a `GOAL` in `REGULATION`/
  `EXTRA_TIME` increments the match score, whereas a `GOAL` in `SHOOTOUT` increments the
  (derived) shootout tally instead. It is the persisted, per-event counterpart of the
  `is_extra_time` live-state flag.

## Core entities

### Player
Represents one squad member.
- `id`, `name`, `position: Position`
- `rating` and a few attribute fields (e.g. `attack`, `defense`, `discipline`,
  `injury_proneness`) — **data only**: passed into the model prompt to inform its event
  decision (including penalty-kick moments), and used to weight the fallback resolver's
  code RNG when a moment degrades; never game logic.
- `availability: AvailabilityStatus`
- `emergency_callup: bool` — `true` for an FR-028 replacement generated on the fly
  (research R12); drives the loud call-up surface. Call-ups are appended to the squad,
  persisted, and never regenerated on reload.
- **Relationships**: belongs to exactly one `Team`.

### AvailabilityStatus
Per-player cross-match state (owned by `availability.py`).
- `state: AvailabilityState`
- `matches_remaining: int` (0 when `AVAILABLE`)
- `accumulated_yellows: int` (tournament yellow count toward the two-yellow ban; cleared
  after QF)
- **Validation**: `matches_remaining >= 0`; `INJURED`/`SUSPENDED` ⇒ `matches_remaining >= 1`.

### Team
- `id`, `name`, `group_id`
- `fifa_ranking: int` — static, real-world FIFA world ranking; used as the tiebreak's
  penultimate key, before drawing of lots (research R7)
- `conduct_points: int` — running FIFA fair-play tally (0 or negative): −1 per yellow, −3
  per second-yellow red, −4 per direct red, −5 for a yellow followed by a direct red,
  summed over the team's group-stage matches. Updated by code at match end from the same
  card outcomes `availability.py` consumes (managed matches: the validated event stream;
  quick-resolved matches: the quick resolver's disciplinary output). Feeds the fair-play
  tiebreak key (research R7).
- `players: list[Player]` (26; may grow past 26 through emergency call-ups, research R12)
- **Relationships**: in one `Group`; one team is the player-managed team.

### Formation
- `name` (e.g. `"4-3-3"`), `slots: list[Position]` of length 11 (position shape)
- Drawn from a fixed menu in `formations.py`; custom formations are out of scope.

### Lineup
The player's per-match selection.
- `formation: Formation`
- `starters: list[Player]` (11, matching the formation's slots)
- `bench: list[Player]`
- **Validation** (`lineup.py`): exactly 11 starters; each starter fills a formation slot of
  its position; every selected player (starters + bench) is `AVAILABLE`; no player appears
  twice. Failure returns an explained rejection (FR-005).

### Match
One fixture. Managed matches carry a live moment stream; AI-vs-AI matches are quick-resolved.
- `id`, `phase: Phase`, `home_team`, `away_team`, `matchday`
- **Live state** (managed matches): `minute`/`moment_index`, `score`, `on_pitch[side]`,
  `subs_used[side]`, `red_cards[side]`, per-player in-match yellows, `is_extra_time`
- `events: list[MatchEvent]` (the resolved, ordered stream)
- `result` (regulation-incl-extra-time score; `winner` and `decided_by` for knockouts; any
  penalty-shootout tally is derived by replaying `SHOOTOUT`-period events, not stored)
- **Relationships**: two `Team`s; produces many `MatchEvent`s and `Substitution`s.

### MatchEvent
One discrete moment's outcome — the atomic unit of a match (FR-007/008).
- `moment_index`, `minute`, `type: EventType`, `commentary: str`
- `actor: Optional[PlayerRef]`, `secondary: Optional[PlayerRef]` (e.g. assist, fouled
  player, sub-in), `team_side`
- `period: MatchPeriod` — code-set phase tag (see enum); how replay separates a shootout
  kick from a regulation goal
- `source: EventSource`
- **Invariants** (enforced in `match/validate.py`): actor is on the pitch for `team_side`,
  **except `OWN_GOAL`** where actor is on the pitch for the side *opposite* `team_side`;
  type is legal for current state; card/injury/sub effects are internally consistent.

### Substitution
- `moment_index`, `team_side`, `player_out`, `player_in`
- **Validation**: `player_out` on pitch; `player_in` on bench and unused; team `subs_used`
  under the limit (5, or 6 if extra time reached) (FR-012/013).

### Group
- `id`, `teams: list[Team]` (4)
- **Resolved (stored)**: `standings` — the group's final ordering, computed **once** when the
  group completes by applying the FIFA tiebreak keys (see `tournament.py`) and then **stored**.
  The final key, **drawing of lots**, is a random draw made only when all deterministic keys
  are exhausted; because the resolved order itself is saved, reload reads it back verbatim
  rather than re-running the tiebreaks — so a resolved standing never re-draws.

### Tournament (root aggregate / save root)
- `managed_team_id`
- `phase: Phase`
- `groups: list[Group]`
- `fixtures: list[Match]`
- `bracket` (knockout pairings once seeded)
- `players_availability` (id → AvailabilityStatus) — the carry-forward table
- `prompt_version: str` and engine I/O log reference
- **Relationships**: owns everything; is the unit of save/load.

## Key state transitions

### Player availability (between matches — `availability.py`)
```
AVAILABLE --(injury event, severity roll)--> INJURED(matches_remaining=k)
AVAILABLE --(red card)--> SUSPENDED(matches_remaining>=1)
AVAILABLE --(2nd tournament yellow, separate matches)--> SUSPENDED(1)   # yellows reset after QF
INJURED(n)  --(match served)--> INJURED(n-1) ... --> AVAILABLE   at 0
SUSPENDED(n)--(match served)--> SUSPENDED(n-1) ... --> AVAILABLE  at 0
```
Applied at match end; decremented per subsequent completed matchday.

### In-match player on-pitch status (`match/engine.py` + `validate.py`)
```
STARTER on-pitch --(subbed off)--> off (no further events; not re-eligible)
STARTER on-pitch --(injury, subs remain)--> off + forced SUBSTITUTION
STARTER on-pitch --(injury, no subs)--> off + team plays a player short
on-pitch --(1st yellow)--> on-pitch (booked)
booked  --(2nd yellow)--> RED --> off (a player short; no replacement)
on-pitch --(straight red)--> off (a player short; no replacement)
```

### Tournament phase (`tournament.py`)
```
GROUP --(all group matches resolved; standings + best-8-third computed)--> R32
R32 --> R16 --> QF --> SF --> THIRD_PLACE --> FINAL --(final resolved)--> DONE
# managed team eliminated at a knockout loss before the SF --> DONE (tournament summary)
# managed team loses the SF --> plays THIRD_PLACE as a managed match --> DONE
```

### Match lifecycle (managed match — `match/engine.py`)
```
KICKOFF -> [CHANCE|GOAL|FOUL|YELLOW|RED|INJURY|SUBSTITUTION|NOTHING]* -> HALF_TIME
        -> [...]* -> FULL_TIME
   (knockout & level) -> EXTRA_TIME -> [...]* -> (level) -> PENALTY_SHOOTOUT
        -> FINAL_WHISTLE (result recorded, events frozen)
```
Substitution windows open at each moment boundary (spec Assumption). Every committed event
originates from `provider→validate` or, after retries, `fallback`.
