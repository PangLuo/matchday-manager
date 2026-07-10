# Feature Specification: World Cup 2026 Team Manager

**Feature Branch**: `001-worldcup-manager`

**Created**: 2026-07-07

**Status**: Draft

**Input**: User description: "Build a minimal single-player football management game where the player manages one national team through the 2026 FIFA World Cup tournament."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Manage one match from lineup to result (Priority: P1)

The player starts a new game, takes charge of a national team, selects a formation and a starting XI plus a bench from that team's available squad, and plays the match. The match unfolds as a readable sequence of discrete moments — each moment produces a commentary event the player reads before the next moment resolves — and builds toward a final score and a post-match report.

**Why this priority**: This is the core loop and the heart of the product. Without the ability to pick a lineup and watch a match resolve moment-by-moment into a plausible result, nothing else in the game has value. It is independently demonstrable as a complete "play one match" experience.

**Independent Test**: Start a new game, get assigned/pick a team, choose a formation and valid starting XI + bench, kick off, and advance through the match's moments to a final whistle. Delivers a full single-match experience with a score and match report.

**Acceptance Scenarios**:

1. **Given** a newly started game, **When** the player chooses a national team, **Then** the game presents that team's squad with each player's position and availability status.
2. **Given** a team's squad, **When** the player assembles a starting XI and bench under a chosen formation, **Then** the game accepts the lineup only if it fits the formation, fields exactly 11 starters, and uses only available players.
3. **Given** an invalid lineup (wrong count, unfilled position, or an unavailable player selected), **When** the player tries to start the match, **Then** the game blocks kickoff and explains what must be corrected.
4. **Given** a valid lineup, **When** the player kicks off, **Then** the match produces a sequence of discrete moment events the player reads one at a time, culminating in a final score and a match report.
5. **Given** the same lineup replayed, **When** the player simulates the match again, **Then** the sequence of events and the result vary rather than repeating identically.

---

### User Story 2 - React to in-match events with substitutions, cards, and injuries (Priority: P2)

During a match, the player manages the game as it develops: making substitutions at stoppages (up to the allowed limit), and dealing with injuries and bookings as they occur. A substituted-off player stops generating events and the incoming player takes over; an injured player must be replaced or the team plays short; cards accumulate and can send a player off, forcing the team to continue a player down.

**Why this priority**: In-match management is what makes the core loop a *game* rather than a spectator sim. It builds directly on P1 (a running match must already exist) and delivers the tactile decision-making that defines the experience.

**Independent Test**: Within a running match, make a substitution at a stoppage and confirm the outgoing player no longer appears in events while the incoming player does; trigger the disciplinary/injury paths and confirm the team's on-pitch count and available bench respond correctly.

**Acceptance Scenarios**:

1. **Given** a running match at a stoppage in play, **When** the player substitutes a bench player for a starter, **Then** the outgoing player generates no further events, the incoming player becomes eligible to, and the used-substitution count increments.
2. **Given** the team has already used its maximum substitutions, **When** the player attempts another substitution, **Then** the game refuses it and states the limit is reached.
3. **Given** a player picks up an injury during play, **When** the stoppage occurs, **Then** the game requires a substitution for that player; if no substitutions remain, the team continues with one fewer player on the pitch.
4. **Given** a player who already has one yellow card in the match, **When** that player receives a second yellow, **Then** it becomes a red card, the player is sent off, and the team plays the rest of the match a player short.
5. **Given** a player receives a straight red card, **When** the sending-off resolves, **Then** the team plays the rest of the match a player short and no substitution can restore the outfield count.
6. **Given** a player has been substituted off, sent off, or is injured out, **When** subsequent moments resolve, **Then** that player can never again be the actor in a match event.

---

### User Story 3 - Progress through the tournament with carried-forward availability (Priority: P3)

Between matches, the player manages their squad for the next fixture, working around players made unavailable by injuries and suspensions carried over from previous matches. The tournament advances through the real 2026 structure — group stage, then a 32-team knockout bracket — and the player advances or is eliminated exactly as the real rules dictate, until they either lose or win the final.

**Why this priority**: Tournament progression turns a set of one-off matches into a full playthrough with stakes and continuity. It depends on P1 and P2 (matches must be playable and produce disciplinary/injury outcomes) and completes the end-to-end game.

**Independent Test**: Play a group match that produces a booking/injury, advance to the next fixture, and confirm the affected player is unavailable for selection; play out enough of the bracket to confirm advancement and elimination follow tournament rules.

**Acceptance Scenarios**:

1. **Given** a player was injured or suspended in a match, **When** the next match's lineup is selected, **Then** that player is shown as unavailable and cannot be placed in the XI or on the bench.
2. **Given** a completed set of group matches, **When** the group stage concludes, **Then** the top two of each group plus the eight best third-placed teams advance to the Round of 32, ranked per tournament rules.
3. **Given** a knockout match that is level at full time, **When** the match must produce a winner, **Then** the tie is resolved so exactly one team advances and the other is eliminated.
4. **Given** the player's team loses a knockout match, **When** the result is confirmed, **Then** the player is eliminated and the game presents a tournament summary.
5. **Given** the player's team wins the final, **When** the result is confirmed, **Then** the game recognises the World Cup as won and presents a tournament summary.
6. **Given** a suspension that spans a defined number of matches, **When** those matches have been served, **Then** the affected player becomes available again for selection.

---

### Edge Cases

- A player must always be able to field a legal XI with a working bench: the game guarantees each managed team has enough available players (accounting for injuries and suspensions) to name 11 starters plus up to 5 bench (the maximum substitutions permitted); if depletion would still drop a team below that floor, the game grants a minimal emergency call-up (just enough replacement players to reach it) rather than forcing a short lineup or a subless bench, and surfaces the call-up to the player loudly.
- Every stoppage-driven substitution requirement (e.g. an injury with substitutions remaining) is resolvable — the game offers eligible bench players and does not deadlock.
- A team reduced to a very low number of players through red cards and injuries mid-match continues to a result (the real-world abandonment threshold is out of scope; the match plays on short).
- Ties in group ranking and in the "best third-placed teams" comparison are broken by the tournament's ordered tiebreak rules. Every rule except the last is deterministic; if teams remain level after all of them, the final **drawing of lots** is a genuine random draw (mirroring FIFA). The resolved group order — including any drawing-of-lots outcome — is recorded once when the group completes and saved, then never recomputed, so a saved/reloaded tournament reads back identically.
- If the underlying match simulation fails to produce a usable event, the game recovers and still advances the match to a valid result rather than stalling.
- The player's own team can finish as a group's third-placed team and either advance (among the best eight) or be eliminated; both branches lead to a coherent next state.
- Replays of the same fixture never produce identical event streams; conversely, a completed match, once resolved, reads back consistently (a saved/finished match does not re-randomise).

## Requirements *(mandatory)*

### Functional Requirements

**Game setup & team selection**

- **FR-001**: The game MUST let the player start a new single-player game and take control of exactly one national team competing in the 2026 World Cup, either by choosing a team or accepting an assigned one.
- **FR-002**: The game MUST present the managed team's squad, showing each player's position and current availability status.
- **FR-003**: The game MUST source squads, groups, and fixtures from data reflecting the real 2026 World Cup; the match simulation MUST be the only thing that determines what happens during a match.

**Lineup & formation selection**

- **FR-004**: The player MUST be able to choose a formation from a set of standard formations and assign available squad players to a starting XI and a bench consistent with that formation.
- **FR-005**: The game MUST validate a lineup before kickoff, rejecting it unless it has exactly 11 starters, satisfies the chosen formation's positional shape, and uses only available (not injured, not suspended) players; the game MUST explain any rejection.
- **FR-006**: The game MUST prevent an unavailable player (injured or suspended) from being selected in the starting XI or on the bench.

**Match simulation as discrete moments**

- **FR-007**: The game MUST simulate each match as a sequence of discrete in-game moments rather than a single-shot score calculation, producing one readable event per moment that the player can read before the next moment resolves.
- **FR-008**: The game MUST accumulate the match's events into a final score and produce a post-match report.
- **FR-009**: Match event streams and results MUST be non-deterministic across replays of the same fixture and lineup — plausible and varied, not repetitive or fixed.
- **FR-010**: Only players currently on the pitch for a team MAY be the acting subject of that team's match events; a player who has been substituted off, sent off, or forced off injured MUST NOT generate further events.

**In-match management**

- **FR-011**: The player MUST be able to make substitutions at any stoppage in play, choosing which bench player replaces which on-pitch starter.
- **FR-012**: The game MUST enforce a maximum of 5 substitutions per team per match (with the additional allowance permitted when a knockout match goes to extra time), and MUST refuse substitutions beyond the limit.
- **FR-013**: When a substitution is made, the game MUST remove the outgoing player from event eligibility, add the incoming player to event eligibility, and record the substitution against the team's used total.

**Injuries & discipline (in-match)**

- **FR-014**: The game MUST be able to produce injuries during a match; an injured player MUST be forced out and require a substitution, and if the team has no substitutions remaining it MUST continue with one fewer player on the pitch.
- **FR-015**: The game MUST be able to produce yellow and red cards during a match; a second yellow card to the same player in a match MUST result in a red card.
- **FR-016**: A player who receives a red card (straight or via two yellows) MUST be sent off, leaving the team a player short for the remainder of the match, and MUST NOT be replaceable by substitution.

**Carry-forward availability (between matches)**

- **FR-017**: Injuries incurred in a match MUST carry forward and make the affected player unavailable for a defined number of following matches.
- **FR-018**: Suspensions — from a red card or from accumulated yellow cards across matches — MUST carry forward and make the affected player unavailable for the next match, consistent with tournament disciplinary rules (including a defined yellow-card accumulation threshold and its reset point).
- **FR-019**: Once an injury or suspension has been served for its defined duration, the game MUST restore the affected player to available status for selection.
- **FR-020**: Between matches, the player MUST be able to revise the formation, starting XI, and bench for the next fixture, working around unavailable players.

**Tournament structure & progression**

- **FR-021**: The tournament MUST follow the real 2026 World Cup structure: 12 groups of 4 teams in a group stage, followed by a 32-team knockout bracket (Round of 32, Round of 16, Quarter-finals, Semi-finals, Final).
- **FR-022**: The game MUST determine group standings and advancement so that the top two teams from each group plus the eight best third-placed teams advance, applying the tournament's ordered tiebreak rules in order; all rules are deterministic except the final drawing of lots, which is a genuine random draw. The resolved group standings MUST be computed once when the group completes and saved, so that reload reads them back verbatim rather than recomputing them (and never re-draws).
- **FR-023**: Knockout matches MUST resolve to a single winner (level scores at full time resolved by the tournament's extra-time and/or shootout rules) so that exactly one team advances.
- **FR-024**: The game MUST advance the player's team through the bracket on a win and eliminate it on a loss, exactly as the real tournament rules dictate.
- **FR-025**: The game MUST end the player's run when their team is eliminated or wins the final, and MUST present a tournament summary in either case.

**End-to-end loop & continuity**

- **FR-026**: The full loop — select lineup → simulate match through discrete moments → manage substitutions/cards/injuries → see result → advance tournament state with updated availability — MUST work end-to-end without manual intervention.
- **FR-027**: The game MUST preserve and reload game state so that a run can be continued, and any resolved outcome — a completed match or a resolved group standing — reads back consistently rather than re-randomising or being recomputed.
- **FR-028**: If a managed team's available players (accounting for injuries and suspensions) would drop below 11 starters plus a bench of up to 5 (the maximum substitutions permitted by FR-012) ahead of a fixture, the game MUST grant that team a minimal emergency call-up — adding only as many replacement players as needed to reach that floor — rather than permitting a short lineup, an illegal lineup, or a bench that leaves no substitution options, and MUST notify the player when a call-up occurs.

### Key Entities *(include if feature involves data)*

- **Tournament**: The single 2026 World Cup run. Holds the current phase (group stage or a specific knockout round), the set of teams, groups, fixtures, and the bracket state.
- **Group**: One of 12 groups of 4 teams. Produces standings used to determine which teams advance and their ranking (including third-placed comparison).
- **Team**: A national team with a squad. One team is managed by the player.
- **Player (Footballer)**: A member of a team's squad, with a position and an availability status (available, injured for N matches, suspended for N matches). Accumulates disciplinary record (yellow cards toward the accumulation threshold, red cards).
- **Squad / Lineup**: The player-chosen configuration for a match — a formation, 11 starters, and a bench — drawn from a team's available players.
- **Formation**: A named positional shape (e.g. standard 4-4-2, 4-3-3, 3-5-2) that constrains how starters are assigned.
- **Match**: A single fixture between two teams. Tracks live state (score, on-pitch players per side, substitutions used, cards, injuries, minute/moment progression), produces an ordered event stream, and resolves to a final score and report; in knockouts it resolves to a single winner.
- **Match Event / Moment**: One discrete in-game moment and its readable commentary (e.g. chance, goal, foul, card, injury, substitution), attributed to on-pitch players.
- **Substitution**: A recorded swap of a bench player for an on-pitch player during a match, counted against the per-match limit.
- **Availability / Disciplinary Record**: The per-player state that carries between matches — active injuries, active suspensions, and accumulated yellow cards — and governs selection eligibility.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A player can start a new game, take a team, and complete a single match — lineup selection through final whistle and match report — as a self-contained experience, with no dead ends.
- **SC-002**: A player can complete an entire tournament run from the first group match to either elimination or winning the final, using only lineup selection and in-match substitutions, without any manual intervention outside the game.
- **SC-003**: Replaying the same fixture with the same lineup produces materially different event streams and outcomes across repeated plays (results are not fixed and commentary is not repetitive), while a match already resolved reads back identically.
- **SC-004**: 100% of substitutions have a visible effect: the substituted-off player produces no further events and the incoming player becomes eligible to, in every match where a substitution is made.
- **SC-005**: 100% of injuries, red cards, and yellow-card accumulations that reach the suspension threshold correctly restrict the affected player's availability in the following match(es), and availability is correctly restored once the duration is served.
- **SC-006**: Group-stage advancement and knockout progression match the real tournament rules in every playthrough: exactly the top two of each group plus the eight best third-placed teams advance, and every knockout match yields exactly one winner.
- **SC-007**: The game never blocks or stalls: every match reaches a valid result and every between-match transition yields a fieldable next lineup, even under injury/card depletion.

## Assumptions

- **Team selection**: The player may choose any of the 48 qualified 2026 World Cup teams (a random/assigned option may also be offered); all teams are managed with the same rules and no artificial difficulty tiers beyond what the squad data implies.
- **Squad data**: Squads use the tournament's 26-player squad size, and each squad contains enough players across positions to field a legal XI throughout a full run under normal injury/suspension attrition. Squad, group, and fixture data reflect the real 2026 World Cup as static data; exact player ratings/attributes are data-driven and not specified here.
- **Emergency call-ups**: The 26-man squad is sized so depletion below a fieldable XI should be near-impossible; the emergency call-up in FR-028 is a last-resort safety valve, not a managed feature — it adds only generic replacement players (no scouting, valuation, or roster browsing), so it does not reopen the "no transfers" scope guardrail.
- **Formations**: A small fixed menu of standard real-world formations is offered; custom/arbitrary formations and tactical instructions beyond formation/lineup/substitutions are out of scope.
- **Substitution windows**: "At any stoppage in play" is modelled as substitutions being permitted at the discrete moment boundaries the simulation exposes, not in continuous real time.
- **Disciplinary model**: Yellow-card accumulation follows the tournament convention (two yellow cards across separate matches trigger a one-match suspension, with accumulated yellows cleared after the quarter-finals); a red card triggers at least a one-match suspension. Injury duration is decided when the injury occurs and spans one or more subsequent matches.
- **Knockout tie resolution**: Level knockout matches are resolved via extra time and, if still level, a penalty shootout, consistent with the real tournament; the sixth substitution is permitted when a match reaches extra time.
- **Scope guardrails (out of scope, per the request)**: No transfers, contracts, finances, or club management; no press conferences, morale/relationship systems, or training/development; no multi-season or multi-tournament play; no multiplayer.
- **Persistence**: The game runs as a single-player experience with saved state so a run can be paused and continued; the exact platform/interface is left to planning.
