# Implementation Plan: World Cup 2026 Team Manager

**Branch**: `001-worldcup-manager` | **Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-worldcup-manager/spec.md`

## Summary

A single-player, terminal-driven game that manages one national team through the 2026
World Cup. The player picks a formation, XI, and bench from available squad players, then
plays each of their team's matches as a sequence of discrete moments. Each moment's event
is **proposed by the Claude API and validated by code before it becomes game state**
(constitution: *code owns truth*). On invalid output or API failure the engine retries a
bounded number of times, then falls back to a **deterministic resolver** so a match always
reaches a valid result (*never stuck*). The deterministic core — calendar, standings,
tiebreaks, best-8-third-place, bracket, knockout tie resolution, and injury/suspension
carry-forward — is plain Python with no model calls and is fully unit-tested (*test the
rules, not the outcomes*). Resolved matches are stored so a finished match reads back
identically and a save reloads without re-calling the model (*replayable*).

**Key scoping decision (not in spec, decided here):** only the **managed team's** matches
run through the moment-by-moment LLM engine. All other (AI-vs-AI) fixtures in the same
matchday are settled by the deterministic quick resolver. This keeps cost, latency, and
API load bounded, and means group tables always fill even when the model is unavailable.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: `anthropic` (Claude API SDK) for the match engine; `pytest` for
tests. Everything else is standard library (`dataclasses`, `json`, `random`, `argparse`,
`enum`, `pathlib`). No web framework, no ORM, no async runtime.

**Storage**: Local JSON files. Bundled static data (teams, 26-man squads, 12 groups,
fixtures) shipped read-only under `src/matchday/data/`; save games written to a
user-writable save directory. No database.

**Testing**: `pytest`. Unit tests cover deterministic logic and the event-validation
contract (including known-bad engine output). Engine tests inject a fake event provider —
**no network calls in the test suite**. Per constitution, tests never assert specific
match scores.

**Target Platform**: Local terminal (macOS / Linux), Python 3.12. Single-player, offline
except for the Claude API call per moment (which is itself degradable to the fallback).

**Project Type**: Single-project CLI application (thin presentation over a pure-logic core).

**Performance Goals**: Interactive play. A moment resolves in roughly the time of one
Haiku API round-trip (~1–2s typical); the fallback resolver is effectively instant. A full
managed-team match resolves within a bounded, small number of discrete moments. No
throughput/concurrency targets — one player, one match at a time.

**Constraints**: Must always reach a valid result even with the model unavailable
(bounded retries → deterministic fallback → surfaced degradation). Prompts are versioned
and every engine input/output is logged. Match temperature is kept low for grounded
commentary; cross-replay variety comes from fresh (unseeded) sampling per simulation, not
from high temperature. No external services beyond the Claude API.

**Scale/Scope**: 48 teams × 26 players; 12 groups of 4; 104 total tournament fixtures
(including the third-place play-off), of which the player plays at most 8 (3 group + up to 5
knockout: R32, R16, QF, SF, then the Final or — after a semi-final loss — the third-place
play-off). Save file holds full tournament state plus resolved event logs for played matches.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Derived from `.specify/memory/constitution.md` v1.0.0. All five principles map to a gate:

| # | Principle | Gate | Status |
|---|-----------|------|--------|
| 1 | **Minimal** | Plain functions + dataclasses; no framework/ORM/abstraction; no package or interface until a second caller exists. | ✅ PASS — stdlib-only core, single injectable seam (the event provider) justified by the test requirement (second caller = the fake). |
| 2 | **Code owns truth** | Every model-proposed event passes an explicit validation contract before mutating match state; invalid output is rejected, never committed. | ✅ PASS — `match/validate.py` is the sole path from proposal to state. |
| 3 | **Test the rules, not the outcomes** | Unit-test calendar, standings, brackets, suspensions, and validation against known-bad output; never assert specific scores. | ✅ PASS — see `research.md` test strategy; deterministic core is pure. |
| 4 | **Never stuck** | Bounded retries → deterministic fallback resolver → surface degradation; game never blocks on the model. | ✅ PASS — `match/fallback.py` + degradation flag on every event source. |
| 5 | **Replayable** | Low temperature, versioned prompts, log every engine I/O, store resolved events, saves reload without re-calling the model. | ✅ PASS — `PROMPT_VERSION` constant, engine I/O log, resolved events persisted. |

**Governance check**: scope stays at one team / one tournament — no club play, seasons,
transfers, or finances. When principles conflict, 2 and 4 beat 1: the validation layer and
the fallback resolver are the two places where a little extra structure is explicitly
allowed. No violations to justify; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-worldcup-manager/
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions & rationale
├── data-model.md        # Phase 1 output — entities & state transitions
├── quickstart.md        # Phase 1 output — run/validate guide
├── contracts/           # Phase 1 output — internal contracts
│   ├── event-schema.md          # model-proposed event shape + validation contract
│   ├── engine-interface.md      # event-provider seam (real vs fake vs fallback)
│   └── save-file-schema.md      # persisted tournament + match-log schema
└── checklists/
    └── requirements.md  # spec quality checklist (from /speckit-specify)
```

### Source Code (repository root)

```text
src/matchday/
├── data/                # bundled static tournament data (read-only JSON)
│   ├── teams.json
│   ├── squads.json
│   ├── groups.json
│   └── fixtures.json
├── models.py            # dataclasses: Player, Team, Squad, Lineup, Formation,
│                        #   Match, MatchEvent, Substitution, AvailabilityStatus, ...
├── formations.py        # the fixed formation menu + positional shape rules
├── lineup.py            # lineup/bench validation against formation + availability
├── availability.py      # injury/suspension carry-forward + yellow accumulation/reset
├── tournament.py        # standings, tiebreaks, best-8-third, bracket, progression
├── knockout.py          # extra-time + penalty-shootout tie resolution
├── quick_resolver.py    # deterministic AI-vs-AI result (non-managed fixtures)
├── match/
│   ├── engine.py        # discrete-moment loop; orchestrates provider→validate→commit
│   ├── prompt.py        # versioned prompt construction (PROMPT_VERSION)
│   ├── provider.py      # EventProvider seam: ClaudeProvider (real) + FakeProvider (tests)
│   ├── validate.py      # event-validation contract (code owns truth)
│   └── fallback.py      # deterministic fallback event resolver
├── persistence.py       # save/load full game state as JSON; engine I/O logging
└── cli.py               # terminal play loop (thin presentation)

tests/
├── unit/                # deterministic logic + validation against known-bad output
│   ├── test_tournament.py
│   ├── test_knockout.py
│   ├── test_availability.py
│   ├── test_lineup.py
│   └── test_validate.py
└── integration/         # full loop with FakeProvider (no network)
    └── test_play_loop.py
```

**Structure Decision**: Single-project CLI. The core (`models`, `tournament`, `knockout`,
`availability`, `lineup`, `formations`, `quick_resolver`) is pure and model-free. The
`match/` sub-package isolates the one risky, model-touching part behind a single seam
(`EventProvider`), which is the only abstraction introduced up front — justified because it
has a second caller by construction (the test fake) and is where principles 2 and 4 live.
`cli.py` stays thin so a richer UI could replace it later without touching the engine.

## Complexity Tracking

> No constitution violations. Section intentionally empty.

## Open Decisions (flagged for confirmation before implementation)

These arise from spec **Assumptions** the plan cannot settle unilaterally. All six below
are now resolved (proposed defaults accepted); kept here as a record of the decision:

1. **Fieldable-XI depletion recovery (spec Edge Cases / FR-028). RESOLVED.** When a managed
   team has fewer than 11 available starters plus a bench covering that fixture's substitution
   allowance, the game performs a minimal **emergency call-up**: it adds just enough
   replacement players (drawn from a generic reserve pool, not a transfer/market mechanic —
   stays within the "no transfers" scope guardrail) to the squad to reach that floor, and
   surfaces this to the player loudly as a rare event. The bench floor matters as much as the
   starters: topping up to exactly 11 would leave a depleted team with zero substitutes,
   meaning the next injury or red card strands them a player short for the rest of that
   match and every match after. The bench floor is sized to the **maximum** substitutions the
   fixture can permit under FR-012 — **five** in a group match (a floor of 16 available
   players) and **six** for a knockout match, which can reach extra time (a floor of 17) — so
   a floored team is never denied a substitution the rules would otherwise grant it. Reaching
   the floor at all is near-impossible given a full 26-man squad (min 23, including ≥3
   goalkeepers); pegging the knockout floor to six costs at most one extra generated reserve
   on this last-resort path and removes the extra-time edge case entirely. This replaces the earlier "start short down to a floor of 7"
   and "risk a lightly-injured player" options — the between-match lineup screen never needs
   to accept an illegal, short, or subless lineup. Replacement-player data (name, attributes)
   is **generated on the fly by the model** and validated/bounded by code, with a
   deterministic generic-reserve fallback — see research R12. See spec FR-028 and Edge Cases.

2. **Injury-duration model (spec Assumptions / FR-017). RESOLVED.** Severity is rolled at
   injury time via weighted RNG — ~60% one match, ~30% two, ~10% tournament-ending — decided
   by code, not the model. This is the `injury event, severity roll` step in the
   `AvailabilityStatus` lifecycle (data-model.md); the exact weights live in code as a
   constant, consistent with other data-driven values (e.g. player ratings) the spec leaves
   unspecified.

3. **AI-vs-AI resolution fidelity (new, introduced by this plan). RESOLVED.** Non-managed
   fixtures are settled by the deterministic quick resolver (attribute-weighted), **not**
   the LLM engine — bounds cost/latency and keeps tables filling under model outage. See
   research R11 and spec Assumptions (Match simulation scope).

4. **FIFA-world-ranking tiebreak key (research R7). RESOLVED.** The real 2026 tiebreak
   sequence uses **FIFA world ranking** as its penultimate key (before drawing of lots); the
   game carries a static `fifa_ranking` field per team and uses it as specified, for fidelity
   to the real rules (accepted over the simpler alternative of dropping the key and leaning
   on drawing-of-lots). See data-model.md (Team) and the save-file schema.

5. **Own-goal representation (contracts/event-schema.md). RESOLVED.** `OWN_GOAL` is added
   to `EventType` as a mirror of `GOAL`: same score-increment-by-code behavior for
   `team_side`, but `actor_id` (the unlucky defender) must belong to the side **opposite**
   `team_side`, and `secondary_id` is always `null` (no assist on an own goal). This replaces
   the earlier gap where the actor-legality rule made own goals unrepresentable — one of the
   known-bad test cases (#3, `actor_id` on the other team) previously rejected exactly this
   shape. See data-model.md (`EventType`, `MatchEvent` invariants) and
   `contracts/event-schema.md` (event-type legality, actor legality, known-bad case #11).

6. **Penalty-shootout representation (contracts/event-schema.md, research R8). RESOLVED.**
   Shootout kicks are ordinary replayable events (R8), so to keep replay from folding shootout
   goals into the regulation scoreline, every committed event gains a code-set `period`
   (`REGULATION | EXTRA_TIME | SHOOTOUT`) — **option A** (a phase tag on the event) over option
   B (distinct `SHOOTOUT_*` event types). A tag is stamped from the match's live
   `current_period` phase state (`REGULATION → EXTRA_TIME → SHOOTOUT`),
   keeps the `EventType` enum and the model's output schema small, and leaves R8's kick-outcome
   vocabulary in `commentary` rather than freezing it into types. The shootout tally is
   **derived** from `SHOOTOUT`-period events (never stored). `result.decided_by` is stored for
   every match: for managed matches it is a validated cache the loader asserts against the
   value derived from the period-tagged events (fail loud) — the same rule as
   `result.home/away`, the stored regulation-incl-extra-time score asserted against replay on
   load — while for quick-resolved matches (which may carry no events) the stored value is
   authoritative. B was rejected for now as it expands the enum/validator/fallback surface and
   is only worth it if per-kick outcomes need to be queryable (e.g. keeper save rates). See
   data-model.md (`MatchPeriod`, `MatchEvent`), `contracts/event-schema.md` (Period & shootout,
   known-bad case #12), and `contracts/save-file-schema.md` (`result` notes).

Settled-by-real-rules (documented, not blocking): yellow accumulation = two yellows across
separate matches → one-match ban, cleared after the quarter-finals; straight/second-yellow
red → at least a one-match ban; knockout ties → extra time then penalties, with the sixth
substitution unlocked at extra time.
