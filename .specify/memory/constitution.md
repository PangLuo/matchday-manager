# Matchday Manager Constitution

A solo, 30-day project: a Championship Manager-style game managing one national team
through World Cup 2026, with matches resolved by an LLM engine. Ship in 30 days; cut
anything that threatens that.

## Principles

1. **Minimal.** Plain functions and explicit data; no abstraction until a second caller
   exists. If it's not needed to ship, don't build it.
2. **Code owns truth.** The LLM proposes match events; code validates them against the
   rules before committing. Invalid output never becomes game state.
3. **Test the rules, not the outcomes.** Unit-test deterministic logic (calendar,
   standings, brackets, suspensions) and validation against known-bad engine output.
   Never assert specific match results — they are probabilistic by design.
4. **Never stuck.** On bad output or API failure: bounded retries, then a deterministic
   fallback resolver, and surface the degradation. The game never blocks on the model.
5. **Replayable.** Low temperature, versioned prompts, log every engine input/output.
   Saves load and continue without re-calling the model.

## Governance

Scope is fixed: one national team, one tournament. No club play, seasons, transfers, or
finances without a MAJOR version bump. When principles conflict, 2 and 4 beat 1. Amend
by editing this file with a semver bump.

**Version**: 1.0.0 | **Ratified**: 2026-07-06 | **Last Amended**: 2026-07-06
