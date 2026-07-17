# Quickstart & Validation Guide

How to run the game and prove the feature works end-to-end. Details live in the linked
contracts and `data-model.md`; this file is the run/validate guide, not implementation.

## Prerequisites

- Python 3.12
- `pip install anthropic pytest`
- Claude API credentials for live play: `export ANTHROPIC_API_KEY=sk-ant-...` (get a key from
  console.anthropic.com). **Not required for the test suite** — tests use `FakeProvider` and
  never hit the network.

## Run the test suite (no credentials needed)

```bash
pytest -q
```

Expected: deterministic-core and validation tests pass. Per constitution principle 3, tests
assert **rule adherence**, never specific match scores.

## Play a game (live engine)

```bash
python -m matchday.cli --new --team ENG        # start a new run managing England
python -m matchday.cli --continue              # resume the saved run
```

The loop per managed match: choose formation → pick XI + bench (only available players) →
play through moments, reacting with substitutions and to cards/injuries → see result →
advance the tournament.

## End-to-end validation scenarios

Each scenario maps to spec success criteria / user stories. Run them to prove the feature.

### V1 — Single match, lineup to result (SC-001, US1)
1. `--new --team ENG`; open the squad — every player shows an availability status
   ([data-model.md](./data-model.md) → AvailabilityStatus).
2. Try an **illegal** lineup (10 starters, or a player out of position) → kickoff is blocked
   with an explanation ([contracts/event-schema.md] rules; FR-005).
3. Submit a legal 4-3-3 → the match streams discrete moment events one at a time and ends
   with a score and match report (FR-007/008).
**Pass**: a full match completes with a readable event stream and a final score.

### V2 — Substitutions visibly change events (SC-004, US2)
1. During a managed match, sub off an on-pitch starter for a bench player at a moment
   boundary.
2. Continue play.
**Pass**: the outgoing player never appears in a later event; the incoming player can
(FR-010/013). A 6th substitution is refused unless the match reached extra time (FR-012).

### V3 — Cards & injuries in-match (US2)
1. Drive (via play, or `FakeProvider` in a test) a player to a **second yellow** →
   resolves to a red; the team continues a player short, no replacement (FR-015/016).
2. Trigger an **injury with no subs remaining** → team plays short, no phantom sub
   (FR-014). Repeat **with** subs remaining → a substitution is required to proceed.
**Pass**: on-pitch counts and bench eligibility match the rules in
[contracts/event-schema.md](./contracts/event-schema.md).

### V4 — Carry-forward availability (SC-005, US3)
1. Finish a match in which a managed player was sent off or injured.
2. Open the **next** match's lineup screen.
**Pass**: that player is shown unavailable and cannot be placed in the XI or bench;
after the suspension/injury duration is served, they become selectable again
(FR-017/018/019; [data-model.md](./data-model.md) transitions).

### V5 — Tournament progression (SC-002/006, US3)
1. Play out the group stage (managed matches live; others quick-resolved — research R11).
**Pass**: exactly the top two of each group plus the eight best third-placed teams advance,
by the ordered tiebreak keys (deterministic except a final random drawing of lots, recorded
once); every knockout tie yields exactly one winner (extra time
→ penalties); a knockout loss ends the run with a summary (a semi-final loss routes through
the third-place play-off first), a final win is recognised as the World Cup won (FR-021–025).

### V6 — Never stuck (SC-007, principle 4)
1. Run the integration test that injects a burst of `ProviderError`s (or play with
   credentials unset so every call fails).
**Pass**: after bounded retries the deterministic fallback resolves each moment, the match
still reaches a final whistle, and the degradation is surfaced (events tagged
`source: FALLBACK`; see [contracts/engine-interface.md](./contracts/engine-interface.md)).

### V7 — Replayable & consistent (SC-003, FR-027)
1. Simulate the same fixture twice from scratch → event streams differ (research R2).
2. Save mid-run, reload → any **finished** match reads back with identical events and score;
   no model call is made to re-render it
   ([contracts/save-file-schema.md](./contracts/save-file-schema.md)).
**Pass**: fresh sims vary; finished matches are immutable on reload.

## Before implementation — decisions record

All five items in [plan.md](./plan.md) → *Open Decisions* are resolved (proposed
defaults accepted); they are retained there only as a record of the decision.
