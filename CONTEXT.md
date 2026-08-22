# CONTEXT — living state

> **Session protocol.** Read `GOAL.md` first, then this file, then act. Update this file
> before ending any session in which something was decided, learned, or built. This file
> is the project's working memory: a session that reads it should be able to resume cold
> without re-deriving anything or re-asking a settled question.

**Current phase:** Phase 0 — Charter · **Status:** complete, pending household review of
the ten principles and twelve domains
**Last updated:** 2026-08-22

---

## Household facts

The accumulating record of who this is being built for. Most of it is captured by the
Phase 3 questionnaire; anything already known is recorded here so it is never re-asked.

| Field | Value |
|---|---|
| Members | Two partners |
| Contact | business@wilinskisolutions.com |
| Preferred names / pronouns | **UNKNOWN — ask before writing either into any document** |
| Move type | Domestic (already living in the US) |
| **Current residence** | **UNKNOWN — highest-value missing fact. See Open Questions #1.** |
| Work situation | Unknown — appears to involve a business (`wilinskisolutions`); confirm whether income is location-independent |
| Budget | Unknown |
| Timeline | Unknown |
| Children | Unknown (current and planned both matter — they weight different domains) |
| Pets | Unknown |
| Stated leaning | Describes the household as "more conservative"; explicitly not ready to turn this into a filter |
| Non-negotiables | None captured yet |

---

## Decision log

Append-only. Each entry: date, decision, rationale. Amendments to `GOAL.md` principles are
recorded here too.

### 2026-08-22 — Move type is domestic
Household is already in the US and moving within it. **Consequence:** visa, immigration,
US credit history, and non-employer healthcare access are dropped as scoring dimensions.
Current residence becomes the baseline every candidate is compared against.

### 2026-08-22 — Universe is the wide net
~3,100 counties plus ~5,000 incorporated places above 5,000 population, enumerated from
Census geography. **Rationale:** the household initially suggested "the top 1,000 places,"
but any pre-made top-N list is itself a popularity ranking — importing one would import
exactly the bias this project exists to remove. Rejected alternatives: metro-only
(~940 CBSAs, too coarse — collapses "Raleigh" into one blob and hides small towns), and
tiered scoring (wide-then-narrow, viable fallback if data volume becomes a problem).

### 2026-08-22 — Sensitive dimensions ingested at weight zero
Household's words: *"I am not quite sure yet about this step, we are more conservative but
I don't want to exclude options yet early on."* **Resolution:** ingest political climate,
religion, diaspora/demographics, and social policy in full; ship every one at weight 0;
expose as explicit toggles. Nothing is pre-decided and nothing becomes unavailable later.
Encoded as Principle 10.

### 2026-08-22 — Sensitive indicators are direction-neutral
The registry stores raw indicators (partisan lean, adherence rate, foreign-born share).
The household's own preference curve decides whether high, low, or a band scores well. The
engine expresses any direction and assumes none. **Rationale:** correctness and neutrality
happen to coincide here — a direction-neutral registry is also the more reusable one.

### 2026-08-22 — The stacking trap is a build requirement
A conservative political preference points at the same Sunbelt metros the internet already
over-promotes, so bias and preference *stack* and would reproduce the original shortlist by
a different route. **Mitigation, required in Phase 4:** every ranking is produced with and
without the political layer, the delta is reported, and high-fit places on the other side
of that axis are always shown. County-level granularity is what makes this real — partisan
lean varies far more within states than between them, so the wide universe offers far more
range than any state-level heuristic.

### 2026-08-22 — Egress policy to be widened rather than working around it
Verified: this environment's proxy returns 403 on CONNECT for every government data host
(census, FEMA, NOAA, BLS, EPA, Zillow, Overpass, County Health Rankings). PyPI and GitHub
are reachable. Household chose to widen the policy — see `docs/network-allowlist.md`.
**The pipeline is written portably regardless**, so the allowlist is an accelerator and
never a dependency.

### 2026-08-22 — Fabricated first name caught and removed
An early draft addressed the household by a first name inferred from the email domain, and
used gendered pronouns that had never been stated. Removed. **Standing rule:** use "the
household" and they/them until told otherwise. Recorded because it is exactly the kind of
plausible-but-unsourced detail Principle 4 exists to catch.

### 2026-08-22 — Phase 0 committed locally; push blocked by GitHub authorization
Phase 0 is committed on `claude/relocation-matching-strategy-wz55sc` but **could not be
pushed**. All three write paths return the same org-level denial, while read access works
(`git ls-remote` succeeds; the repo is empty, zero branches):

| Path | Result |
|---|---|
| `git push` | 403 — "Claude doesn't have GitHub access to this repo for your organization" |
| GitHub MCP contents API | 403 — "Resource not accessible by integration" |
| Re-attach with push access | `already_present` — no new credentials granted |

**Remedy (either one):** an org admin installs the Claude GitHub App at
`https://github.com/apps/claude/installations/select_target`, **or** the account owner
reconnects GitHub at `https://claude.ai/customize/connectors?auth_start=github&auth_start_force=1`
to re-link an existing installation.

Until then the commit exists only in an ephemeral container. A git bundle was handed to the
household so the full commit history can be restored with
`git clone wlm-phase0.bundle` or `git pull wlm-phase0.bundle`.

---

## Data inventory

Nothing ingested yet — Phase 0 built no pipeline by design. `docs/data-sources.md` holds
the full catalog with URLs, vintages, geography levels, and licenses. This table tracks
ingest state and is filled in during Phase 2.

| Source | Geo level | Vintage | Coverage | Status |
|---|---|---|---|---|
| _(none yet)_ | | | | Phase 2 |

---

## Indicator registry status

| Metric | Count |
|---|---|
| Domains defined | 12 — 10 scoring, 2 questionnaire-only (`config/domains.yaml`) |
| Sources registered | 34 (`config/sources.yaml`) |
| Indicators registered | 42 seed (`config/indicators.yaml`) — expands to 40–60 populated in Phase 2 |
| Indicators carrying provisional curve params | 11 — placeholders awaiting Phase 3 elicitation |
| Indicators populated with data | 0 |

Validate with `make validate`; the invariants are enforced mechanically and the negative
cases are covered by `make test` (24 tests).

---

## Open questions and known unknowns

1. **Where does the household currently live?** The single highest-value missing fact.
   For a domestic move it sets the baseline every candidate is scored against, it anchors
   the calibration set, and it determines what "better" even means. First question of the
   Phase 3 questionnaire; ask sooner if the chance arises.
2. **Preferred names and pronouns** — see the 2026-08-22 decision above.
3. **Is household income location-independent?** Decides whether the career/economy domain
   is weighted heavily or nearly zeroed, which shifts a large share of the total weight.
4. **Children — current and planned.** Schools, childcare cost, and family services are
   ~3 of 12 domains; the answer materially changes the ranking.
5. **Which sensitive dimensions get switched on, and when.** Deliberately left open.
   Revisit after the household has seen a ranking without them.
6. **Buy or rent on arrival?** Changes whether purchase price or rent drives the cost domain.
7. **Crime data coverage.** FBI CDE reporting is agency-voluntary and patchy. Decide in
   Phase 2 whether to flag gaps, substitute a modeled estimate, or down-weight the safety
   domain where coverage is thin. Must not be silently imputed (Principle 6).

---

## Next actions

0. **Restore Phase 0 into the repo.** Grant GitHub write access (see the 2026-08-22
   decision above), then push the branch — or restore from the `wlm-phase0.bundle` handed
   over. Everything else is blocked on the work being somewhere durable.
1. **Household reviews the ten principles in `GOAL.md` and the twelve domains in
   `config/domains.yaml`.** These are the two things most expensive to change later; Phase 1
   should not start until both are confirmed.
2. **Add the hostnames in `docs/network-allowlist.md`** to the environment's egress policy.
3. **Begin Phase 1 — Universe:** build the fixed candidate set from the Census Gazetteer
   and CBSA delineation files, commit it, and prove the pipeline end-to-end on three or
   four sources before scaling ingest.
4. **Capture current residence** at the earliest opportunity (Open Question #1).
