# Contract: Save-File Schema

One JSON file is the whole game (research R10). Reload restores state and replays stored
events for any finished match **without re-calling the model** (FR-027). Storing resolved
events (not RNG seeds) is what makes a finished match read back identically.

## Top-level shape

```jsonc
{
  "schema_version": 1,
  "prompt_version": "v1",
  "managed_team_id": "ENG",
  "phase": "GROUP",                       // Phase enum
  "rng_note": "live sim is unseeded; seeds appear only in tests",

  "teams": { "ENG": { "id": "ENG", "name": "England", "group_id": "B", "fifa_ranking": 4, "players": [ /* Player */ ] }, /* ... */ },

  "availability": {                        // carry-forward table, id -> AvailabilityStatus
    "p_1023": { "state": "SUSPENDED", "matches_remaining": 1, "accumulated_yellows": 0 },
    "p_1044": { "state": "INJURED",   "matches_remaining": 2, "accumulated_yellows": 1 }
  },

  "groups": [ { "id": "B", "team_ids": ["ENG","..."], "standings": [ /* resolved once when the group completes: ordered team_ids + P/W/D/L/GF/GA/Pts, incl. any drawing-of-lots outcome; read back verbatim on reload, never recomputed (research R7) */ ] } ],

  "bracket": { "R32": [ { "match_id": "K01", "home": "ENG", "away": "..." } ], "R16": [], "QF": [], "SF": [], "FINAL": [] },

  "fixtures": [ /* Match records, see below */ ],

  "engine_log": [ /* append-only engine I/O entries, see below */ ]
}
```

## Match record

```jsonc
{
  "id": "M17",
  "phase": "GROUP",
  "matchday": 2,
  "home_team": "ENG",
  "away_team": "...",
  "managed": true,                         // false => quick-resolved AI-vs-AI
  "status": "FINAL",                       // SCHEDULED | IN_PROGRESS | FINAL
  "result": { "home": 2, "away": 1, "winner": "ENG", "decided_by": "normal" },
                                           // decided_by: normal | extra_time | penalties
  "lineup": {                              // player's selection for managed matches
    "formation": "4-3-3",
    "starters": ["p_1001","..."],
    "bench": ["p_1020","..."]
  },
  "events": [                              // ordered, frozen once status == FINAL
    { "moment_index": 0, "minute": 0,  "type": "KICKOFF",      "team_side": null,   "actor_id": null,    "secondary_id": null, "period": "REGULATION", "commentary": "…", "source": "MODEL" },
    { "moment_index": 7, "minute": 23, "type": "GOAL",         "team_side": "home", "actor_id": "p_1009","secondary_id": "p_1007", "period": "REGULATION", "commentary": "…", "source": "MODEL" },
    { "moment_index": 9, "minute": 31, "type": "SUBSTITUTION", "team_side": "home", "actor_id": "p_1009","secondary_id": "p_1020", "period": "REGULATION", "commentary": "…", "source": "MODEL" }
    // knockout events may carry "period": "EXTRA_TIME" or "SHOOTOUT"; a SHOOTOUT GOAL feeds
    // the (derived) penalty tally, never home/away below
  ]
}
```

Notes:
- For `managed: false` matches, `events` MAY be empty; `result` is the **authoritative**
  quick-resolver output (nothing to replay).
- A `FINAL` match's `events`/`result` are **immutable** on reload — the engine reads them,
  never regenerates them.
- No *per-event* running tallies (score-so-far, cards-so-far, subs-used) are stored; they are
  recomputed by replaying `events`, keeping code as the single source of truth on load too.
- `result` fields that **are** stored, and how they relate to the event stream:
  - `winner` / `decided_by` are stored authoritatively (a penalty/extra-time outcome, incl.
    the shootout tally, is derived from `SHOOTOUT`/`EXTRA_TIME`-period events; `decided_by` is
    `penalties` if any `SHOOTOUT` event exists, else `extra_time` if any `EXTRA_TIME` event
    exists, else `normal`).
  - For `managed: true`, `home`/`away` are the regulation-incl-extra-time scoreline and **MUST
    equal** the replay of `REGULATION`/`EXTRA_TIME` goals (`SHOOTOUT` goals excluded). The
    loader asserts this and **fails loud** on mismatch (principle 4) — the stored scoreline is
    a validated cache, never a second source of truth.

## Engine I/O log entry (principle 5: log every engine input/output)

```jsonc
{
  "match_id": "M17",
  "moment_index": 7,
  "prompt_version": "v1",
  "request_digest": "…prompt text or a hash + params (model, temperature)…",
  "response": { /* raw ProposedEvent as returned */ },
  "source": "MODEL",                       // MODEL | FALLBACK
  "rejections": ["actor p_1009 not on pitch"]  // reasons for any rejected attempts this moment
}
```

## Compatibility & safety

- `schema_version` gates future migrations; loaders reject unknown higher versions rather
  than silently mis-reading (fail loud, principle 4).
- `prompt_version` recorded at top level and per log entry so a bumped prompt never
  invalidates the interpretation of an old save.
- The save is a single file written atomically (temp file + rename) so an interrupted write
  never corrupts an existing save.
