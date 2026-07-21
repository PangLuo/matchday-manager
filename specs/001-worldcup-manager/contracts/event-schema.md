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
set score, minute, cards-count, subs-used, or `period` — those are **derived by code** from
the validated event and the current match phase, so the model can never directly write
authoritative counters. In particular the model never marks a kick as a shootout kick; code
stamps `period` from the phase the match is in, so a plain `GOAL` proposed during the
shootout is simply tagged `SHOOTOUT` — there is no model-confusion path to guard against.

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
- `GOAL`: `actor_id` (scorer) required and on-pitch; increments a score by code — the
  **regulation score** when `period` is `REGULATION`/`EXTRA_TIME`, or the **shootout tally**
  when `period` is `SHOOTOUT` (see Period & shootout below). `actor_id` MUST belong to
  `team_side`.
- `OWN_GOAL`: mirrors `GOAL` — increments `team_side`'s score by code — but `actor_id`
  (the defender) MUST belong to the side **opposite** `team_side`, and MUST be on-pitch.
  `secondary_id` MUST be `null` (no assist on an own goal). Illegal during `SHOOTOUT`
  (no own goals in a real shootout — see Period & shootout).
- `CHANCE` / `FOUL`: narrative moments with no counter effects — `actor_id` required and
  on-pitch for `team_side` (generic actor legality); for `FOUL`, an optional `secondary_id`
  (the fouled player) MUST be on-pitch for the **opposite** side. No score/card/sub state
  changes; discipline arrives only via a separate `YELLOW`/`RED` event.
- `YELLOW`: `actor_id` on-pitch and not already sent off. If the player **already has a
  yellow this match**, the event is upgraded by code to a `RED` (FR-015) — the validator
  emits the red effect, not the model.
- `RED` (straight): `actor_id` on-pitch; player leaves, side goes a player short, and is
  **not replaceable** (FR-016).
- `INJURY`: `actor_id` on-pitch; player must leave. If subs remain, a `SUBSTITUTION` is
  required to proceed; if none remain, the side continues a player short (FR-014).
- `SUBSTITUTION`: see substitution rules below.
- `NOTHING` / period markers (`KICKOFF`, `HALF_TIME`, `FULL_TIME`, `EXTRA_TIME`,
  `PENALTY_SHOOTOUT`, `FINAL_WHISTLE`): no actor required; always legal when the clock is in
  the right phase. A period marker also advances the code-owned `period` (`EXTRA_TIME` →
  `EXTRA_TIME`, `PENALTY_SHOOTOUT` → `SHOOTOUT`); the advance happens **before** the
  marker's own `period` stamp, so a period-advancing marker is tagged with the period it
  opens (data-model.md, `MatchPeriod`). `HALF_TIME` occurs at the regulation
  interval (minute 45) and again at the extra-time interval (minute 105), distinguished on
  replay by the code-stamped `period` (`REGULATION` vs `EXTRA_TIME`); it is a pure clock
  marker and never advances `current_period`. **Exception**: during `SHOOTOUT`, a
  `NOTHING` is a missed kick and the kick-attribution rules below apply.

### Period & shootout (research R8)
- Code stamps every committed event with `period` from the match's current phase; the model
  never sets it.
- Penalty-shootout kicks are ordinary moments resolved by the same engine, tagged
  `period == SHOOTOUT`. A scored kick is a `GOAL`; a missed/saved kick is a `NOTHING` whose
  manner (saved, wide, high, off the post) lives in `commentary`. As in the real shootout
  there are no rebounds and no own goals — `OWN_GOAL` is illegal during `SHOOTOUT`
  (known-bad case #14). Shootout goals increment the **shootout tally**, never the
  regulation score.
- **Event-type legality during `SHOOTOUT`**: the only legal types are `GOAL`, `NOTHING`
  (a missed kick), and the `PENALTY_SHOOTOUT`/`FINAL_WHISTLE` markers — `CHANCE`, `FOUL`,
  `YELLOW`, `RED`, `INJURY`, `SUBSTITUTION`, `OWN_GOAL`, and all other markers are rejected
  (known-bad case #15).
- **Kick attribution (required during `SHOOTOUT`)**: every committed event except the
  `PENALTY_SHOOTOUT`/`FINAL_WHISTLE` markers represents exactly one kick and MUST carry
  `team_side` (the kicking side) and `actor_id` (the kicker, on-pitch for that side) — a
  missed/saved kick's type is `NOTHING`, but its actor is still the kicker. Code owns the
  kick order; the
  validator rejects a kick attributed to the side whose turn it is not. This attribution is
  what makes the derived tally and the mathematically-decided stop condition (best-of-5 →
  sudden death, R8) computable from the event stream alone.
- The shootout tally is **derived** by replaying `SHOOTOUT`-period goals — it is not stored.
- `result.decided_by` is stored, but for managed matches it is a validated cache: the loader
  re-derives it — `penalties` if any `SHOOTOUT` event exists, else `extra_time` if any
  `EXTRA_TIME` event exists, else `normal` — and asserts it equals the stored value (fail
  loud), the same rule `save-file-schema.md` applies to `result.home/away`. For quick-resolved
  matches (no events to derive from) the stored value is authoritative.
- No substitutions occur during `SHOOTOUT`; the sixth substitution unlocks at `EXTRA_TIME`
  (FR-012).

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
- No substitutions are legal once `period == SHOOTOUT`.
- On commit (by code): move player_out off (permanently ineligible), player_in on,
  increment `subs_used`.
- A sent-off player MUST NOT be replaced (the short-handed state persists).

### What code derives after a successful validate (never the model)
`score`, shootout tally, `period`, `minute`/`moment_index`, per-player in-match yellows,
`subs_used`, `red_cards`, `on_pitch` sets, and `source`. This is the concrete boundary of
*code owns truth*.

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
12. `SUBSTITUTION` proposed while `period == SHOOTOUT` → MUST reject (subs are closed once the
    shootout begins).
13. During `period == SHOOTOUT`: a kick event (`GOAL` or miss-`NOTHING`) with a null
    `team_side` or `actor_id`, or attributed to the side whose turn it is not → MUST reject
    (kick attribution is what the derived tally and stop condition are computed from).
14. `OWN_GOAL` proposed while `period == SHOOTOUT` → MUST reject (no own goals in a real
    shootout; a deflected-in kick is simply the kicker's `GOAL`).
15. Any non-kick, non-marker type (`CHANCE`, `FOUL`, `YELLOW`, `RED`, `INJURY`, …) proposed
    while `period == SHOOTOUT` → MUST reject (only `GOAL`, miss-`NOTHING`, and the
    `PENALTY_SHOOTOUT`/`FINAL_WHISTLE` markers are legal during the shootout).
