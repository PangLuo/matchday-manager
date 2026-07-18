# Phase 0 Research: World Cup 2026 Team Manager

All Technical Context unknowns resolved below. Each entry: **Decision → Rationale →
Alternatives considered.**

## R1. Match-engine model choice

**Decision**: Use **Claude Haiku 4.5** (`claude-haiku-4-5`) for per-moment event
proposals, at a **low temperature** (~0.6). One request per discrete moment.

**Rationale**: A managed-team match is many small, structured, low-stakes calls (one per
moment). Haiku 4.5 is the cheapest/fastest tier ($1 / $5 per 1M tokens, 200K context) and
— unlike the 4.6+ adaptive-only family — still accepts the `temperature` parameter, which
the "low temperature for grounded commentary" constraint (constitution principle 5)
requires. The user explicitly asked for a cheap/fast model for many small low-temperature
calls, which overrides the default of Opus.

**Alternatives considered**:
- *Opus 4.8 / Sonnet 5* — higher quality narration but 15–25× the input cost and slower;
  wasteful for a two-sentence event, and their tier drops `temperature` (adaptive-only),
  removing the determinism dial the constitution asks for.
- *One call for the whole match* — rejected by the spec: matches MUST be a sequence of
  discrete moments (FR-007), and a single call cannot interleave the player's
  substitutions/reactions between moments.

## R2. Reconciling "low temperature / replayable" with "varied across replays"

**Decision**: The **model decides what each moment is** — chance, foul, card, or nothing —
reasoning over on-pitch player attributes, match progress, scoreline, and momentum; **code
validates** the proposed event for legality (R4) and commits it. Keep temperature low
(~0.6) for grounded commentary. Cross-replay variety (FR-009, SC-003) comes from (a)
unseeded stochastic sampling on each fresh simulation, and (b) an optional per-moment
code-supplied "luck" value passed into the prompt as a variance nudge — randomness stays
code-owned, but the *decision* is the model's. The attribute-weighted code RNG survives
only as the deterministic **fallback** resolver (R5) — which also covers shootout kicks when
a moment degrades, since kicks run through the same per-moment loop (R8) — never the primary
path. A **resolved** match stores its events and is never re-simulated on
reload (FR-027).

**Rationale**: This is principle 2 read literally — "the LLM *proposes* match events; code
*validates* them." Letting the model weigh attributes + full match state holistically yields
richer, more contextual football than a code-side rhythm table, without hardcoding
event-selection rules, and it matches what `contracts/event-schema.md` already specifies
(the model sets `type`). The apparent conflict with principle 5 dissolves once "replay" is
read correctly: *re-simulating* is a new run with fresh sampling → different stream;
*reloading* a finished match replays stored events → identical. Low temperature keeps each
event plausible and grounded in the state it is given; the evolving state, unseeded
sampling, and the luck nudge supply the variety. Code still owns *truth* — validation plus
all authoritative counters (event-schema.md §1) — it just no longer owns the *choice*.

**Risks & mitigations**:
- *Outcome calibration / balance* — the model's implicit sense of how often a weak side
  scores against a strong one may be miscalibrated, and principle 3 forbids unit-testing
  outcomes. Mitigate by feeding **numeric attributes** into the prompt and manually
  spot-checking score distributions over many sims; the fallback RNG is an
  attribute-anchored reference point.
- *Variety at low temperature* — a low-temp model may gravitate to the same "likely"
  events. Mitigate with the per-moment luck nudge (b), so variance enters through
  code-owned inputs while the decision stays with the model.

**Alternatives considered**:
- *Code-side RNG decides the event, model only narrates* (the earlier R2) — rejected:
  over-constrains beyond principle 2, hardcodes match rhythm, and contradicts
  event-schema.md, which already lets the model set `type`. Demoted to the fallback role.
- *High temperature for variety* — rejected: degrades plausibility and fights principle 5;
  variety comes from code-owned inputs instead.
- *Deterministic seed per fixture* — rejected: would make replays identical, violating
  FR-009. Seeds are used only where reproducibility is desired (tests), never in live play.

## R3. Structured event output from the model

**Decision**: Request the moment event as a **schema-constrained structured output** via
`client.messages.parse()` with an explicit event schema (`output_config.format`). Code then
**re-validates** the parsed object against game rules (R4) before committing — schema
validity is necessary but not sufficient.

**Rationale**: `messages.parse()` guarantees the response is well-formed JSON matching the
event shape, eliminating a class of parse failures cheaply. But structural validity ≠ rule
validity (the model can name an off-pitch player in a perfectly-shaped object), so
principle 2 still requires the code-owned validation contract. Two layers, distinct jobs.

**Alternatives considered**:
- *Tool use with `strict: true`* — equivalent structural guarantee; `messages.parse()` is
  simpler for a pure request→object shape with no tool-execution loop.
- *Free-text + regex parsing* — rejected: brittle, and exactly the fragility principle 4
  warns against.

## R4. Event-validation contract (code owns truth)

**Decision**: A single pure function `validate(event, match_state) -> Ok | Reject(reason)`
is the only path from a proposed event to committed state. It enforces, at minimum:
- The actor(s) belong to the acting team and are **currently on the pitch** (not subbed
  off, sent off, or injured out). (FR-010)
- The event type is legal for the current state (e.g. a goal names a valid scorer; a
  substitution references an on-pitch starter out and an eligible bench player in).
- Card logic: a second yellow to the same player in the match **becomes a red** (FR-015);
  a red removes the player and forbids replacement (FR-016).
- Substitution legality: within the per-team limit of 5 (+1 in extra time), bench player
  unused, not already off. (FR-012/FR-013)
- Injury forces the player out and requires a sub, or short-handed if none remain. (FR-014)

Invalid → the event is rejected (never committed), the engine retries (R5).

**Rationale**: Centralizing every rule in one pure, unit-testable function is the concrete
form of principle 2 and directly enables principle 3 (test the rules, incl. known-bad
input). Full field-by-field contract in `contracts/event-schema.md`.

**Alternatives considered**:
- *Trusting schema/model output* — rejected outright by principle 2.
- *Scattering checks across the engine* — rejected: unauditable and untestable in isolation.

## R5. Retry + deterministic fallback (never stuck)

**Decision**: Per moment: call the provider; if the call **fails** (API error/timeout) or
the returned event is **rejected** by validation, retry up to **N=2** times (fresh call).
If still unresolved, invoke the **deterministic fallback resolver** (`match/fallback.py`),
which produces a guaranteed-legal event from match state + a local RNG weighted by player
attributes (including the legitimate "nothing happens, clock advances" event). Every event
carries its **source** (`model` | `fallback`) and the degradation is surfaced to the player
and logged.

**Rationale**: This is principle 4 verbatim: bounded retries → deterministic fallback →
surface. The fallback is also reused as the AI-vs-AI quick resolver's per-moment core, so
one resolver serves both "model degraded" and "match we don't narrate."

**Terminology note**: "deterministic" for the fallback and quick resolver means
**model-free and code-owned**, not bit-identical across runs — both sample a local RNG
(unseeded in live play, per R2/FR-009; seeded in tests, so under test they *are*
reproducible). The guarantee is that they always produce a legal result without the model,
not that they produce the same one.

**Alternatives considered**:
- *Unbounded retries* — rejected: can hang the game on a persistent outage.
- *Abort the match on failure* — rejected: violates "never blocks," corrupts tournament
  state.

## R6. Isolating & mocking the model client for tests

**Decision**: Define a narrow `EventProvider` seam (a callable/Protocol:
`propose(match_state, prompt_version) -> ProposedEvent`). `ClaudeProvider` wraps the
`anthropic` client; `FakeProvider` returns scripted events (including deliberately
**known-bad** ones) for tests. The engine depends only on the seam. **No test touches the
network**; the real client is constructed only in `cli.py`/production wiring.

**Rationale**: One injection point makes the engine fully testable and satisfies principle 3
without mocking library internals. It is the single up-front abstraction the plan allows,
justified because it has a real second caller (the fake) — consistent with principle 1's
"no abstraction until a second caller exists."

**Alternatives considered**:
- *Monkeypatching the SDK* — rejected: couples tests to SDK internals, brittle across SDK
  updates.
- *Hitting the live API in tests* — rejected: non-deterministic, slow, costly, offline-
  hostile, and would tempt outcome assertions (violating principle 3).

## R7. Deterministic tournament core

**Decision**: Pure functions over dataclasses for: fixture/calendar ordering; group
standings with the **2026 FIFA-ordered tiebreaks** — overall **points**, then for teams
level on points a head-to-head mini-table among only those teams (**h2h points → h2h goal
difference → h2h goals scored**), then **overall goal difference → overall goals scored →
fair-play (team-conduct) score → FIFA world ranking → drawing of lots** as the final key
(the fair-play score is the per-team `conduct_points` tally accrued by code at match end —
see data-model.md, Team);
ranking the **best 8 third-placed** teams; seeding the 32-team bracket
(R32 → R16 → QF → SF → third-place play-off → Final); and knockout progression. No model calls anywhere in this
layer.

**Rationale**: These are exactly the deterministic rules principle 3 says to unit-test.
Keeping them pure and model-free makes them trivially testable and immune to engine
degradation. Note the 2026 change: **head-to-head is applied before overall goal
difference** (unlike pre-2026 World Cups), and it is a three-key mini-table over just the
tied teams, not a single key — a common implementation gotcha. When three teams are level,
the head-to-head table is built from results among those three only, then re-split if that
partially separates them. Every key **except the last is deterministic**; if teams remain
level after all of them, the final **drawing of lots** is a genuine random draw (mirroring
the real competition, per user decision). The draw uses an **injectable RNG** — unseeded in
live play, seeded in tests. To keep this replayable (principle 5), the group's **resolved
standing is computed once when the group completes and then stored** (the save's
`groups[].standings`); reload reads that ordering back verbatim rather than re-running the
tiebreaks, so a resolved standing never re-draws and reads back identically — the conclusion
is stored, mirroring how a match's final `result` is stored alongside its events (FR-027).
Consequently the tiebreak unit tests assert determinism only up to the lot step and inject a
fixed seed to exercise the draw (principle 3).

**Alternatives considered**:
- *Deterministic final tiebreak (no real draw)* — rejected: does not mirror the real
  competition, which resolves fully-level teams by drawing lots (per user decision).
  Reproducibility and testability are instead secured by storing the resolved order and
  seeding the RNG in tests, not by removing the randomness.
- *Recompute the standings on every load instead of saving them* — rejected. Here the group
  order is not stored; it is re-derived from the saved match results each time the game loads.
  But the last tiebreak (drawing of lots) is random, so to make that re-derivation land the
  same way every reload we would also have to save each team's drawn lot number in a separate
  `drawn_lots` map and feed it back in. Saving the finished order directly avoids all of that:
  no extra field, and it matches how a match saves its final `result` rather than recomputing
  the score from its events.

## R8. Knockout tie resolution

**Decision**: Level knockout matches continue to **extra time** (two further periods of
moments, resolved by the same per-moment engine as regular play) and, if still level, a
**penalty shootout**. Each kick is itself an ordinary moment through the same
provider-proposes/code-validates/fallback-on-failure loop (R5/R6). As in the real shootout,
a kick resolves to either a goal or a miss (no rebounds, no own goals — `OWN_GOAL` is
illegal during the shootout); the *manner* of a miss (saved, wide, high, off the post) lives
in the event's `commentary` rather than a flat score/miss coin-flip, so kicks carry the same
narrative nuance as in-game chances. Code
bounds the shootout by ordinary kick-count bookkeeping (best-of-5 per side, then sudden
death, stopping as soon as the result is mathematically decided), which is what guarantees
**exactly one winner** (FR-023), not a constraint on what each kick's outcome can be. That
bookkeeping needs every kick — scored or missed — attributed: during the shootout the
validator requires `team_side` and `actor_id` on every kick event and enforces the
code-owned kick order (see event-schema.md, Period & shootout). The
**sixth substitution** unlocks when a match reaches extra time (FR-012). Every committed
event is code-tagged with its `MatchPeriod` (`REGULATION | EXTRA_TIME | SHOOTOUT`) so replay
keeps shootout kicks out of the regulation scoreline: a `SHOOTOUT` goal feeds the derived
penalty tally, never `result.home/away` (see data-model.md and contracts/event-schema.md).

**Rationale**: Mirrors real 2026 knockout rules and guarantees single-winner progression by
reusing the one per-moment engine implementation everywhere instead of introducing a second,
narrower resolution path just for shootouts. It also means a shootout degrades the same way
regular play does: bounded retries then the deterministic fallback (R5), whose miss
commentary varies (saved, wide, high, off the post) so a model-down shootout still feels
plausible.

**Alternatives considered**:
- *Bespoke attribute-weighted deterministic-with-RNG shootout resolver, separate from the
  moment engine* — rejected: duplicates the provider/validate/fallback/retry machinery R5
  already provides, and flattens each kick to a bare score/miss with none of the narrative
  nuance (saved, wide, high, off the post) that ordinary moments already handle.
- *Coin-flip resolution* — rejected: ignores squad quality and feels arbitrary.
- *Replay matches* — rejected: not the tournament format.

## R9. Availability carry-forward

**Decision**: Per-player `AvailabilityStatus` carries between matches: `available`,
`injured(matches_remaining)`, `suspended(matches_remaining)`, plus an
`accumulated_yellows` counter. Transitions applied at match end and decremented as matches
are served, restoring availability at zero (FR-017/018/019). Yellow rule: two yellows in
separate matches → one-match ban; accumulated yellows **cleared after the quarter-finals**.
Red (straight or second-yellow) → at least a one-match ban. Injury duration per plan
open-decision #2.

**Rationale**: Encapsulates all cross-match player state in one tested module (principle 3),
consuming per-match disciplinary/injury outputs from the validated event stream.

**Alternatives considered**:
- *Recomputing suspensions from full history each time* — rejected: more complex than
  carrying a small decrementing counter; no benefit.

## R10. Persistence / save schema

**Decision**: Save the entire game as JSON: tournament state (phase, groups, standings,
bracket), the managed team id, per-player availability, and a **resolved event log per
played match** plus the raw **engine I/O log** (prompt version, request, response, source).
Reload restores state and replays stored events for review — **never re-calling the model**
for a finished match (FR-027). Schema in `contracts/save-file-schema.md`.

**Rationale**: Storing resolved events (not seeds) is what makes a finished match read back
identically (principle 5) and decouples reload from model availability. The engine I/O log
satisfies "log every engine input/output."

**Alternatives considered**:
- *Store only an RNG seed and re-simulate on load* — rejected: a model-driven stream is not
  reproducible from a seed, so reload could diverge — violating FR-027.
- *SQLite* — rejected: over-engineered for one save file; violates principle 1.

## R11. Managed vs. AI-vs-AI match fidelity (scope decision)

**Decision**: Only the **managed team's** fixtures use the moment-by-moment LLM engine.
Every other fixture on the same matchday is settled by the **deterministic quick resolver**
(attribute-weighted score + minimal disciplinary/injury outcomes), so all 12 group tables
and the bracket always advance.

**Rationale**: 104 total fixtures × many moments each would be prohibitively slow/expensive
and pointless — the player never watches them. Quick-resolving them bounds cost/latency and
keeps tables filling even during a model outage (principle 4). Flagged as plan open-decision
#3 because it is not stated in the spec.

**Alternatives considered**:
- *LLM-simulate every fixture* — rejected: cost/latency/API-load blow-up for zero player-
  visible benefit.
- *Fully random other results* — rejected: ignores squad quality, making the bracket feel
  arbitrary; attribute-weighting is barely more code and much more plausible.

## R12. Emergency call-up player generation (FR-028)

**Decision**: When the between-match floor check (11 available starters + a bench matching the
fixture's substitution allowance — 5 in the group stage, 6 in the knockouts, FR-028) fails,
**code decides** how many replacement players are needed and at which
positions; the **model generates** each replacement's flavor — name and attribute values —
through the same propose→validate→commit pattern as match events (structured output via
`messages.parse()`). Code validates every proposal: the requested position is honored,
attributes fall within a code-defined modest band (below the squad's average rating), the
name is non-empty and unique within the squad; ids are **code-assigned**, never the
model's. On rejection or API failure: the same bounded-retry policy as moments, then a
deterministic fallback that mints a generic reserve ("Reserve DEF" style, baseline
attributes) so a model-down call-up still succeeds (principle 4). Committed call-ups are
appended to the team's squad flagged `emergency_callup: true`, persisted in the save, and
never regenerated on reload (principle 5). The call-up is surfaced loudly (spec Edge Cases).

**Rationale**: Reuses the established provider→validate→fallback machinery instead of
introducing new data assets: no static reserve-pool file to author and maintain for 48
teams for a near-impossible event (principle 1), while code still owns the trigger, count,
positions, ids, and attribute bounds (principle 2). Generated names/attributes keep the
loud call-up moment immersive. Stays within the "no transfers" guardrail — no scouting,
valuation, or roster browsing (spec Assumptions).

**Alternatives considered**:
- *Static bundled reserve-pool data per team* — rejected: authoring 48 teams of reserve
  data for a last-resort path is wasted effort and dead weight in `src/matchday/data/`.
- *Pure code-generated generic reserves as the primary path* — rejected as primary: bland
  placeholder names in a deliberately loud, player-facing moment; retained verbatim as the
  deterministic fallback.
