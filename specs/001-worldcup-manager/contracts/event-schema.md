# Contract: Match Event Schema & Validation

Two layers, distinct jobs (research R3/R4): the **schema** guarantees the model returns a
well-formed object; the **validation contract** guarantees the object is *legal for the
current match state* before it becomes game state. Both must pass; schema-valid ≠ legal.

## 1. Proposed-event schema (model output shape)

Requested via `client.messages.parse()` with `output_config.format`. The model proposes
**one** event per moment. Fields the model MAY set:

```jsonc
{
  "type": "GOAL",                 // one of EventType (see data-model)
  "team_side": "home",            // "home" | "away" | null (for neutral events)
  "actor_id": "p_1023",           // primary player id, or null
  "secondary_id": "p_1044",       // assist / fouled / sub-in, or null
  "commentary": "…one or two sentences…"
}
```

Constraints baked into the schema: `type` is an enum; ids are strings or null;
`commentary` is a bounded-length string. The schema deliberately does **not** let the model
set score, minute, cards-count, or subs-used — those are **derived by code** from the
validated event, so the model can never directly write authoritative counters.

## 2. Validation contract (`match/validate.py`)

```
validate(proposed: ProposedEvent, state: MatchState) -> Ok(CommittedEvent) | Reject(reason)
```

Pure function. MUST enforce every rule below. On any failure → `Reject(reason)` (the engine
then retries, then falls back — see `engine-interface.md`). Rejection reasons are strings
for logging/tests.

### Actor legality (FR-010)
- If `actor_id` is set: the player exists, is **currently on the pitch** (started or subbed
  on, and not subbed off / sent off / injured out), and belongs to `team_side` — **except
  `OWN_GOAL`**, whose `actor_id` must belong to the side opposite `team_side` instead.
- A player who has left the pitch by any means can never be `actor_id` or `secondary_id`
  again.

### Event-type legality (per current state)
- `GOAL`: `actor_id` (scorer) required and on-pitch; increments that side's score by code.
  `actor_id` MUST belong to `team_side`.
- `OWN_GOAL`: mirrors `GOAL` — increments `team_side`'s score by code — but `actor_id`
  (the defender) MUST belong to the side **opposite** `team_side`, and MUST be on-pitch.
  `secondary_id` MUST be `null` (no assist on an own goal). (plan.md Open Decisions #5)
- `YELLOW`: `actor_id` on-pitch and not already sent off. If the player **already has a
  yellow this match**, the event is upgraded by code to a `RED` (FR-015) — the validator
  emits the red effect, not the model.
- `RED` (straight): `actor_id` on-pitch; player leaves, side goes a player short, and is
  **not replaceable** (FR-016).
- `INJURY`: `actor_id` on-pitch; player must leave. If subs remain, a `SUBSTITUTION` is
  required to proceed; if none remain, the side continues a player short (FR-014).
- `SUBSTITUTION`: see substitution rules below.
- `NOTHING` / period markers (`KICKOFF`, `HALF_TIME`, `FULL_TIME`, `EXTRA_TIME`,
  `FINAL_WHISTLE`): no actor required; always legal when the clock is in the right phase.

### Card accounting
- A player's in-match yellow count is owned by code, incremented on a validated `YELLOW`.
- Second yellow ⇒ red ⇒ off, a player short, no replacement.
- Tournament-level `accumulated_yellows` is updated at match end by `availability.py`, not
  here.

### Substitution rules (FR-011/012/013)
- `player_out` (=`actor_id`) is on the pitch for `team_side`.
- `player_in` (=`secondary_id`) is on that team's bench and has not been used.
- `subs_used[team_side] < limit`, where `limit = 5`, or `6` once the match has entered extra
  time.
- On commit (by code): move player_out off (permanently ineligible), player_in on,
  increment `subs_used`.
- A sent-off player MUST NOT be replaced (the short-handed state persists).

### What code derives after a successful validate (never the model)
`score`, `minute`/`moment_index`, per-player in-match yellows, `subs_used`, `red_cards`,
`on_pitch` sets, and `source`. This is the concrete boundary of *code owns truth*.

## 3. Known-bad inputs the validator MUST reject (test corpus, principle 3)

These become `test_validate.py` cases:
1. `actor_id` names a player already **subbed off**.
2. `actor_id` names a **sent-off** player.
3. `actor_id` belongs to the **other** team than `team_side` (for any type except
   `OWN_GOAL`, where the reverse is required — see case 11).
4. `SUBSTITUTION` when `subs_used == limit`.
5. `SUBSTITUTION` bringing on an **already-used** or **starting** player.
6. `SUBSTITUTION` bringing on a player to **replace a sent-off** player (illegal restore).
7. `GOAL` with `actor_id == null` or an unknown id.
8. `YELLOW` to a player who already has one → MUST resolve to a `RED` effect, not a second
   yellow.
9. `type` outside the `EventType` enum (rejected at schema layer; validator also guards).
10. Injury with no subs remaining → MUST yield short-handed, never a phantom substitution.
11. `OWN_GOAL` with `actor_id` belonging to `team_side` itself (must be the opposite side),
    or with a non-null `secondary_id` (no assist on an own goal).
