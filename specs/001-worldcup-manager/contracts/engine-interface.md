# Contract: Engine Interface (Event-Provider Seam)

The one abstraction introduced up front (research R6). It isolates the model-touching code
behind a narrow seam so the engine is fully testable offline and so the retry→fallback
policy (principle 4) lives in one place.

## The seam

```python
class EventProvider(Protocol):
    def propose(self, state: MatchState, prompt_version: str) -> ProposedEvent | ProviderError:
        ...
```

- **`ClaudeProvider`** (production, in `match/provider.py`): builds the versioned prompt
  (`match/prompt.py`), calls `client.messages.parse(model="claude-haiku-4-5",
  temperature≈0.6, output_config=...)`, returns a `ProposedEvent` or a `ProviderError` on
  API failure/timeout. Constructed **only** in `cli.py` / production wiring.
- **`FakeProvider`** (tests, in `match/provider.py` or `tests/`): returns scripted events —
  including deliberately known-bad ones and injected `ProviderError`s — with **no network**.

The engine depends only on `EventProvider`; it never imports the `anthropic` client
directly.

## Per-moment resolution policy (`match/engine.py`)

```
for each moment until the match/period ends:
    attempt = 0
    while attempt <= MAX_RETRIES (=2):
        result = provider.propose(state, PROMPT_VERSION)
        if result is ProviderError:            # API failure/timeout
            attempt += 1; continue
        decision = validate(result, state)      # contracts/event-schema.md
        if decision is Ok:
            commit(decision); event.source = MODEL; break
        else:
            log_rejection(decision.reason); attempt += 1; continue
    else:
        event = fallback.resolve(state)          # deterministic, always legal
        commit(event); event.source = FALLBACK
        surface_degradation()                    # user-visible + logged
    append event to match.events; log engine I/O (request, response, source, reason?)
    open a substitution window (player may act before the next moment)
```

Guarantees:
- **Bounded**: at most `MAX_RETRIES+1` model calls per moment, then a deterministic result.
- **Never stuck**: the `else` branch always commits a legal event, so every match reaches
  `FINAL_WHISTLE` even with the model fully down (principle 4).
- **Auditable**: every committed event records `source`; every attempt is logged with its
  rejection reason if any (principle 5).

## Fallback resolver contract (`match/fallback.py`)

```python
def resolve(state: MatchState) -> CommittedEvent   # never raises, never rejects
```

- Uses only `state` + a local RNG weighted by on-pitch player attributes.
- Produces a **guaranteed-legal** event for the current state, including the legitimate
  `NOTHING` (clock advances) outcome — so it can always make progress.
- Never proposes an illegal actor, an over-limit substitution, or a replacement for a
  sent-off player (it is bound by the same rules the validator enforces).
- Reused as the per-moment core of the AI-vs-AI **quick resolver** (research R11).

## Prompt versioning (`match/prompt.py`)

- A module-level `PROMPT_VERSION` constant (e.g. `"v1"`); every engine I/O log entry records
  it. Changing the prompt bumps the constant so logs/saves remain interpretable (principle 5).

## Testability summary (principle 3)

- Unit: `validate` against the known-bad corpus (`event-schema.md` §3); `fallback.resolve`
  legality invariants; tournament/knockout/availability/lineup pure logic.
- Integration: full play loop driven by `FakeProvider` — scripted goals, cards, an injury
  with and without subs remaining, a provider-error burst forcing fallback, and a
  substitution whose outgoing player then (illegally) appears and is rejected. **No test
  asserts a specific final score** — only rule adherence and structural outcomes.
