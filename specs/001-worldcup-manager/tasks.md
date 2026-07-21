# Tasks: World Cup 2026 Team Manager

**Input**: Design documents from `/specs/001-worldcup-manager/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the constitution (principle 3) and plan mandate unit tests for the
deterministic core, the known-bad validation corpus (`contracts/event-schema.md` §3), and
FakeProvider-driven integration tests with no network calls. Tests never assert specific
match scores.

**Organization**: Tasks are grouped by user story to enable independent implementation and
testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- All paths are relative to the repository root

## Path Conventions

Single-project CLI per plan.md: `src/matchday/` (core + `match/` sub-package + bundled
`data/`), `tests/unit/`, `tests/integration/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton and bundled static tournament data

- [ ] T001 Create project structure: `src/matchday/__init__.py`, `src/matchday/match/__init__.py`, `src/matchday/data/` (empty), `tests/unit/__init__.py`, `tests/integration/__init__.py` per plan.md Project Structure
- [ ] T002 Initialize Python 3.12 project in `pyproject.toml`: package metadata, `anthropic` dependency, `pytest` dev dependency, pytest configuration (testpaths), `src/` layout
- [ ] T003 [P] Author static data `src/matchday/data/teams.json` and `src/matchday/data/groups.json`: 48 qualified 2026 teams with `id`, `name`, `group_id`, `fifa_ranking`; 12 groups (A–L) of 4 team ids (spec FR-003, FR-021; data-model Team/Group)
- [ ] T004 [P] Author static data `src/matchday/data/squads.json`: 26-player squads for all 48 teams — `id`, `name`, `position` (GK/DEF/MID/FWD, ≥3 GK per squad), `rating`, `attack`, `defense`, `discipline`, `injury_proneness` (spec Assumptions squad data; data-model Player)
- [ ] T005 [P] Author static data `src/matchday/data/fixtures.json`: all 104 fixtures — 72 group matches with matchdays, plus the knockout template (R32, R16, QF, SF, third-place play-off, Final) with slot references for bracket seeding (spec FR-021; contracts/save-file-schema.md bracket shape)

**Checkpoint**: `pip install -e .` succeeds; data files parse as JSON

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core types and data loading that every user story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 Define all enums and dataclasses in `src/matchday/models.py`: `Position`, `Phase`, `AvailabilityState`, `EventType` (incl. `OWN_GOAL`, `NOTHING`, period markers), `EventSource`, `MatchPeriod`; `Player` (incl. `emergency_callup`), `AvailabilityStatus`, `Team` (incl. `fifa_ranking`, `conduct_points`), `Formation`, `Lineup`, `Match` (live state incl. `current_period`), `MatchEvent` (incl. code-set `period`, `source`), `Substitution`, `Group` (incl. stored `standings`), `Tournament` (incl. `players_availability`, `prompt_version`) — exactly as specified in data-model.md
- [ ] T007 [P] Implement the fixed formation menu in `src/matchday/formations.py`: named formations (e.g. 4-4-2, 4-3-3, 3-5-2, 4-2-3-1) each as 11 `Position` slots (spec FR-004; data-model Formation; makes T009 pass)
- [ ] T008 Implement new-game bootstrap in `src/matchday/persistence.py`: load bundled `teams.json`/`squads.json`/`groups.json`/`fixtures.json` into a fresh `Tournament` (all players AVAILABLE, empty bracket, group-phase fixtures scheduled); full save/load comes later in T041 (depends on T006)

**Checkpoint**: A `Tournament` can be constructed in-memory from bundled data — user story implementation can now begin

---

## Phase 3: User Story 1 - Manage one match from lineup to result (Priority: P1) 🎯 MVP

**Goal**: Start a new game, pick a team, choose formation + XI + bench with validation, and
play a full match as a stream of discrete moment events (model-proposed, code-validated,
fallback-guaranteed) ending in a final score and match report.

**Independent Test**: Start a new game, pick a team, submit an invalid lineup (blocked with
explanation), submit a valid one, advance moment-by-moment to the final whistle, see score
and report. Replaying the same fixture yields a different event stream.

### Tests for User Story 1 ⚠️ write first, ensure they FAIL before implementation

- [ ] T009 [P] [US1] Unit tests for formation menu shape rules in `tests/unit/test_formations.py`: every formation has exactly 11 slots including exactly one GK
- [ ] T010 [P] [US1] Unit tests for lineup validation in `tests/unit/test_lineup.py`: exactly-11 rule, formation-slot position fit, only-AVAILABLE players, no duplicates, bench eligibility, explained rejections (FR-004/005/006; data-model Lineup validation)
- [ ] T011 [P] [US1] Unit tests for core event validation in `tests/unit/test_validate.py`: actor on-pitch legality, `GOAL` scorer rules, `OWN_GOAL` opposite-side actor + null `secondary_id`, `CHANCE`/`FOUL` narrative rules, period markers, known-bad corpus cases #3, #7, #9, #11 from contracts/event-schema.md §3
- [ ] T012 [P] [US1] Unit tests for fallback legality invariants in `tests/unit/test_fallback.py`: seeded RNG, `fallback.resolve` always returns a legal event for arbitrary match states (never an off-pitch actor), including the legitimate `NOTHING` outcome (contracts/engine-interface.md fallback contract)

### Implementation for User Story 1

- [ ] T013 [US1] Implement lineup/bench validation in `src/matchday/lineup.py`: validate `Lineup` against formation slots and the tournament's `players_availability` table, returning explained rejections (FR-005; makes T010 pass)
- [ ] T014 [P] [US1] Implement versioned prompt construction in `src/matchday/match/prompt.py`: module-level `PROMPT_VERSION = "v1"` and `MATCH_TEMPERATURE = 0.4` (low for grounded commentary, non-zero so fresh per-replay sampling still yields varied streams per FR-009), prompt from match state (on-pitch players with numeric attributes, scoreline, minute, momentum, code-supplied luck nudge per research R2)
- [ ] T015 [P] [US1] Define the provider seam in `src/matchday/match/provider.py`: `ProposedEvent`, `ProviderError`, `EventProvider` Protocol (`propose(state, prompt_version)`), and `FakeProvider` returning scripted events/errors for tests (contracts/engine-interface.md)
- [ ] T016 [US1] Implement `ClaudeProvider` in `src/matchday/match/provider.py`: `client.messages.parse(model="claude-haiku-4-5", temperature=prompt.MATCH_TEMPERATURE, output_config=...)` with the proposed-event schema from contracts/event-schema.md §1 (type/team_side/actor_id/secondary_id/commentary only), returning `ProviderError` on API failure/timeout (depends on T014, T015)
- [ ] T017 [US1] Implement core event validation in `src/matchday/match/validate.py`: pure `validate(proposed, state) -> Ok(CommittedEvent) | Reject(reason)` covering actor legality (incl. `OWN_GOAL` opposite-side rule), `GOAL`/`OWN_GOAL` score-increment-by-code, `CHANCE`/`FOUL`/`NOTHING`/period-marker legality, string rejection reasons (contracts/event-schema.md §2; makes T011 pass)
- [ ] T018 [US1] Implement deterministic fallback resolver in `src/matchday/match/fallback.py`: `resolve(state) -> CommittedEvent`, local RNG (injectable seed for tests) weighted by on-pitch player attributes, guaranteed-legal output incl. `NOTHING` (contracts/engine-interface.md; makes T012 pass)
- [ ] T019 [US1] Implement the discrete-moment engine in `src/matchday/match/engine.py`: per-moment loop `provider.propose → validate → commit` with `MAX_RETRIES = 2` then fallback, `source` tagging, degradation surfacing, code-stamped `period`/minute/moment_index/score, `KICKOFF → … → HALF_TIME → … → FULL_TIME → FINAL_WHISTLE` regulation lifecycle, in-memory engine I/O log entries (request digest, response, source, rejection reasons), and post-match report accumulation (FR-007/008; contracts/engine-interface.md resolution policy)
- [ ] T020 [US1] Implement the terminal play loop in `src/matchday/cli.py`: `python -m matchday.cli --new [--team ID]` — team choice or assignment, squad display with positions + availability (FR-001/002), formation/XI/bench selection with rejection explanations, moment-by-moment playback (one event per keypress), final score + match report; wire `ClaudeProvider` here only (research R6). Add `src/matchday/__main__.py` or module-run support so `python -m matchday.cli` works
- [ ] T021 [US1] Integration test for a full match in `tests/integration/test_play_loop.py`: drive the engine with `FakeProvider` through a scripted full match (goals, own goal, narrative moments) to `FINAL_WHISTLE`; include a `ProviderError` burst forcing fallback with `source: FALLBACK` and surfaced degradation; assert rule adherence and structure only, never a specific score (quickstart V1/V6)

**Checkpoint**: A complete single match is playable end-to-end — MVP demonstrable

---

## Phase 4: User Story 2 - React to in-match events with substitutions, cards, and injuries (Priority: P2)

**Goal**: In-match management — substitutions at moment boundaries within the limit, yellow
→ second-yellow red upgrades, straight reds, injuries forcing subs or short-handed play,
and permanent event-ineligibility for players off the pitch.

**Independent Test**: In a running match, make a substitution and confirm the outgoing
player never acts again while the incoming player can; exhaust the sub limit and see a
refusal; drive second-yellow, straight-red, and injury (with and without subs remaining)
paths and confirm on-pitch counts respond correctly.

### Tests for User Story 2 ⚠️ write first, ensure they FAIL before implementation

- [ ] T022 [P] [US2] Extend `tests/unit/test_validate.py` with the substitution/card/injury known-bad corpus: cases #1 (subbed-off actor), #2 (sent-off actor), #4 (sub past limit), #5 (re-using a used/starting player), #6 (replacing a sent-off player), #8 (second yellow resolves to red effect), #10 (injury with no subs → short-handed, no phantom sub) from contracts/event-schema.md §3
- [ ] T023 [P] [US2] Extend `tests/integration/test_play_loop.py` with scripted US2 scenarios via `FakeProvider`: a substitution whose outgoing player later (illegally) appears and is rejected; a second-yellow red; a straight red; an injury with subs remaining (forced substitution) and one without (team plays short) (quickstart V2/V3)

### Implementation for User Story 2

- [ ] T024 [US2] Add substitution validation to `src/matchday/match/validate.py`: `player_out` on pitch, `player_in` on bench and unused, `subs_used < limit` (5; 6 once extra time reached), sent-off players never replaceable; commit moves players and increments `subs_used` (FR-011/012/013)
- [ ] T025 [US2] Add card and injury validation to `src/matchday/match/validate.py`: code-owned in-match yellow counts, second yellow upgraded by code to a red effect, straight red → off + a player short + irreplaceable, injury → forced off with required substitution if subs remain else short-handed (FR-014/015/016; makes T022 pass)
- [ ] T026 [US2] Extend `src/matchday/match/engine.py`: open a substitution window at every moment boundary accepting player-initiated subs, enforce the forced-substitution stoppage after an injury, maintain `on_pitch`/`red_cards`/`subs_used` sets so departed players are permanently event-ineligible (FR-010)
- [ ] T027 [US2] Extend `src/matchday/match/fallback.py` to propose card/injury/`SUBSTITUTION` events legally under the same state constraints the validator enforces (never an over-limit sub, never restoring a sent-off player), keeping degraded matches rule-complete
- [ ] T028 [US2] Extend `src/matchday/cli.py`: substitution prompt at each moment boundary (list eligible bench players, refuse past the limit with the reason), display bookings/reds/injuries and the team's on-pitch count as they happen

**Checkpoint**: US1 and US2 both work — a match is now interactively manageable

---

## Phase 5: User Story 3 - Progress through the tournament with carried-forward availability (Priority: P3)

**Goal**: Full tournament continuity — availability carry-forward, group standings with the
2026 tiebreaks, best-8-third ranking, bracket seeding and knockout progression with extra
time/shootouts, quick-resolved AI-vs-AI fixtures, emergency call-ups, and save/load.

**Independent Test**: Play a group match producing a booking/injury, advance, and confirm
the player is unavailable next match and restored after serving the duration; play out the
bracket and confirm advancement/elimination follow tournament rules; save and reload
mid-run with finished matches reading back identically.

### Tests for User Story 3 ⚠️ write first, ensure they FAIL before implementation

- [ ] T029 [P] [US3] Unit tests for availability carry-forward in `tests/unit/test_availability.py`: injury severity roll (seeded weighted RNG ~60/30/10), red-card and two-yellow suspensions, per-matchday decrement and restore at zero, yellow reset after QF (FR-017/018/019; data-model availability transitions)
- [ ] T030 [P] [US3] Unit tests for the deterministic tournament core in `tests/unit/test_tournament.py`: 2026 tiebreak order (points → h2h mini-table points/GD/goals among tied teams incl. three-way re-split → overall GD → goals → conduct points → FIFA ranking → seeded drawing of lots), best-8-third ranking, bracket seeding, standings stored once on group completion and never recomputed (FR-022; research R7)
- [ ] T031 [P] [US3] Unit tests for knockout resolution and shootout validation in `tests/unit/test_knockout.py`: extra time on level full-time, sixth sub unlocked at extra time, shootout kick order + best-of-5 → sudden-death stop condition, derived tally from `SHOOTOUT`-period events, known-bad corpus cases #12–#15 (FR-023; research R8; contracts/event-schema.md Period & shootout)
- [ ] T032 [P] [US3] Unit tests for the quick resolver in `tests/unit/test_quick_resolver.py`: seeded runs produce legal results, attribute-weighting favors stronger sides distributionally, disciplinary/injury outputs feed availability and `conduct_points` (research R11)
- [ ] T033 [P] [US3] Unit tests for call-up generation in `tests/unit/test_callups.py`: floor check (16 group / 17 knockout), code-computed needs, proposal validation (position honored, attribute band below squad average, unique non-empty name, code-assigned ids), generic-reserve fallback, `emergency_callup` flag (FR-028; research R12)
- [ ] T034 [P] [US3] Unit tests for persistence in `tests/unit/test_persistence.py`: save→load round-trip, atomic write, `schema_version` gating (reject unknown higher versions), loader fail-loud assertions (`result.home/away` vs event replay, `decided_by` re-derivation for managed matches), finished matches immutable, call-ups never regenerated (FR-027; contracts/save-file-schema.md)

### Implementation for User Story 3

- [ ] T035 [US3] Implement availability carry-forward in `src/matchday/availability.py`: apply match-end outcomes (injury severity roll via injectable RNG with the 60/30/10 weights constant, red/two-yellow suspensions, `accumulated_yellows` with post-QF reset), decrement per completed matchday, update `Team.conduct_points` from card outcomes (makes T029 pass)
- [ ] T036 [US3] Implement the deterministic tournament core in `src/matchday/tournament.py`: group standings with the full ordered tiebreak keys and injectable-RNG drawing of lots, standings computed once on group completion and stored on `Group.standings`, best-8-third ranking, 32-team bracket seeding, phase progression `GROUP → R32 → … → FINAL → DONE` incl. the SF-loss → third-place route (FR-021/022/024; makes T030 pass)
- [ ] T037 [US3] Add shootout-period validation to `src/matchday/match/validate.py`: during `SHOOTOUT` only `GOAL`/miss-`NOTHING`/markers legal, mandatory kick attribution (`team_side` + on-pitch `actor_id`, marker exemption), code-owned kick-order enforcement, `OWN_GOAL` and `SUBSTITUTION` rejected (known-bad #12–#15)
- [ ] T038 [US3] Implement knockout tie resolution in `src/matchday/knockout.py` and extend `src/matchday/match/engine.py`: `EXTRA_TIME` and `PENALTY_SHOOTOUT` period transitions (advance-before-stamp per data-model `MatchPeriod`), extra-time `HALF_TIME` marker, sixth-sub unlock, kick-count bookkeeping stopping when mathematically decided, exactly-one-winner guarantee, `decided_by` recorded (FR-023; makes T031 pass)
- [ ] T039 [US3] Implement the AI-vs-AI quick resolver in `src/matchday/quick_resolver.py`: attribute-weighted result reusing the fallback resolver's per-moment core, minimal disciplinary/injury outputs, authoritative `result` with possibly-empty events (research R11; makes T032 pass)
- [ ] T040 [US3] Implement emergency call-ups: `propose_callups(team, needs, prompt_version)` in `src/matchday/match/provider.py` (ClaudeProvider structured output + FakeProvider), code-side floor check/needs computation/validation/id-assignment in `src/matchday/availability.py`, retry-then-generic-reserve fallback (FR-028; contracts/engine-interface.md call-up section; makes T033 pass)
- [ ] T041 [US3] Complete save/load in `src/matchday/persistence.py`: full `Tournament` serialization per contracts/save-file-schema.md (teams, availability, groups with stored standings, bracket, fixtures with lineup/events/result, append-only engine I/O log), atomic temp-file+rename write, `schema_version`/`prompt_version` recording, loader fail-loud validation of cached `result` fields, no model calls on load (FR-027; makes T034 pass)
- [ ] T042 [US3] Extend `src/matchday/cli.py` for the tournament loop: `--continue` to resume a save, between-match lineup revision around unavailable players (FR-020), matchday advancement (managed match live, others quick-resolved), loud emergency call-up announcement, elimination/third-place-route/champion tournament summary (FR-024/025/026)
- [ ] T043 [US3] Integration test for a full tournament run in `tests/integration/test_tournament_run.py`: `FakeProvider`-driven run from first group match to elimination and to winning the final — carry-forward availability visible in the next lineup, group advancement per rules, knockout single-winner, save/reload mid-run with identical read-back of finished matches, never-stuck under a provider outage (SC-002/005/006/007; quickstart V4/V5/V7)

**Checkpoint**: All user stories independently functional — full game playable end-to-end

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation against the quickstart guide and final tidy-up

- [ ] T044 Run all eight quickstart validation scenarios (V1–V8) from specs/001-worldcup-manager/quickstart.md against the built game and fix any failures
- [ ] T045 [P] Write the project README.md: install, `pytest -q`, play instructions (`--new --team ENG`, `--continue`), API-key setup, and the model-down degradation behavior
- [ ] T046 [P] Review engine I/O logging end-to-end: every moment logs prompt version, request digest, response, source, and rejection reasons per contracts/save-file-schema.md engine-log shape

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T003/T004/T005 parallel after T001
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**; T007 parallel with T006; T008 after T006
- **User Story 1 (Phase 3)**: After Foundational; delivers the MVP
- **User Story 2 (Phase 4)**: After Foundational; extends US1's files (`validate.py`, `engine.py`, `fallback.py`, `cli.py`), so in practice runs after US1
- **User Story 3 (Phase 5)**: After Foundational; new modules (T035, T036, T039) can start in parallel with US2, but T037/T038/T040/T042 touch US1/US2 files and run after them
- **Polish (Phase 6)**: After all user stories

### Within Each User Story

- Tests are written first and must fail before implementation
- US1: T013–T018 before T019 (engine composes them); T019 before T020; T021 last
- US2: T024 → T025 (same file), then T026 → T027 → T028
- US3: T035/T036/T039 independent; T037 before T038; T040 after T035; T041 after T036/T038; T042 after T039/T040/T041; T043 last

### Parallel Opportunities

- **Setup**: T003, T004, T005 (three data files)
- **Foundational**: T006 ∥ T007
- **US1 tests**: T009, T010, T011, T012 together; then T014 ∥ T015 during implementation
- **US2 tests**: T022 ∥ T023
- **US3 tests**: T029–T034 (six test files) together; then T035 ∥ T036 ∥ T039
- **Polish**: T045 ∥ T046

---

## Parallel Example: User Story 1

```bash
# Write all US1 tests together (different files):
Task: "Unit tests for formation menu shape rules in tests/unit/test_formations.py"
Task: "Unit tests for lineup validation in tests/unit/test_lineup.py"
Task: "Unit tests for core event validation in tests/unit/test_validate.py"
Task: "Unit tests for fallback legality invariants in tests/unit/test_fallback.py"

# Then build the independent seam pieces together:
Task: "Implement versioned prompt construction in src/matchday/match/prompt.py"
Task: "Define the provider seam in src/matchday/match/provider.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (skeleton + static data)
2. Complete Phase 2: Foundational (models, formations, bootstrap) — blocks everything
3. Complete Phase 3: User Story 1 (tests → lineup → seam → validate/fallback → engine → CLI)
4. **STOP and VALIDATE**: quickstart V1 (single match lineup-to-result) and V6 (never stuck)
5. Demo: one full playable match

### Incremental Delivery

1. Setup + Foundational → a `Tournament` constructs from data
2. US1 → one playable match with model-proposed, code-validated moments (MVP)
3. US2 → substitutions, cards, injuries make it a game (validate with quickstart V2/V3)
4. US3 → full tournament with carry-forward, knockouts, saves (validate with V4/V5/V7/V8)
5. Polish → all eight quickstart scenarios green

### Notes

- No test touches the network — engine tests inject `FakeProvider`; RNG is seeded only in tests, never in live play
- No test asserts a specific match score (constitution principle 3)
- `ClaudeProvider` is constructed only in `cli.py` production wiring (research R6)
- Commit after each task or logical group; stop at any checkpoint to validate the story independently
