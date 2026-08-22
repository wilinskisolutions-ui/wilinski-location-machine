# CONTEXT — living state

> **Session protocol.** Read `GOAL.md` first, then this file, then act. Update this file
> before ending any session in which something was decided, learned, or built. This file
> is the project's working memory: a session that reads it should be able to resume cold
> without re-deriving anything or re-asking a settled question.

**Current phase:** Phase 1 — Universe · **Status:** built and tested; runs on synthetic
fixtures only, because the data hosts are still blocked
**Blocking Phase 2:** the network allowlist (`docs/network-allowlist.md`)
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

### 2026-08-22 — Phase 0 pushed to `main` (push blocker: RESOLVED)
Phase 0 is on GitHub at `main`, commit `751a3d7`, 31 files.

**Branch decision:** pushed to `main` rather than a feature branch, on the household's
explicit instruction. The repo was completely empty — no commits, no default branch — so
the charter is the repo's starting point and `main` became default automatically. Future
phases branch from it normally.

**The blocker, and why it is worth remembering.** The first push attempts were refused by
the git proxy with *"Claude doesn't have GitHub access to this repo for your
organization"*, while `list_repos` simultaneously reported `can_push: true` and
`git ls-remote` succeeded. Those disagree because they are **two different identities**:
the household's own GitHub account (which has write rights) and the Claude GitHub App (the
automation identity, which did not). Read access working is not evidence that write access
will. Access resolved on a later attempt without a settings change, so it was most likely
a stale credential in the session rather than a missing installation.

**If it recurs:** confirm which identity is failing before changing anything. A 403 that
survives a fresh session means the Claude GitHub App needs installing for this repo at
`https://github.com/apps/claude/installations/select_target`, or the connector needs
re-linking at `https://claude.ai/customize/connectors?auth_start=github&auth_start_force=1`.
A repeated 403 is a policy denial, never a transient — do not retry it in a loop.

### 2026-08-22 — Principles and domains approved; education and safety restructured
The household reviewed the ten principles and the domains and approved them, flagging
education and safety as possibly missing. **They were present but were the two thinnest
domains** (3 and 2 indicators), and education was hidden inside a domain labelled "Family
and education". The instinct was right even though "missing" was not. Four decisions
followed, all taken before Phase 3 elicits weights, when config changes are still cheap:

1. **Education split into its own domain.** `family_services` (weight 10) became
   `education` (6) and `family_childcare` (4). Schools and childcare previously shared one
   weight, which made it impossible to say that one matters and the other does not.
   Domains: 12 → 13. Education indicators: 3 → 6.
2. **School quality is measured by growth, not raw achievement.** Stanford's SEDA publishes
   learning rates — how much students improve per year. District proficiency correlates
   heavily with family income, so a raw-score ranking would largely measure how wealthy the
   neighbours are and call it school quality, then collide with the cost domain by pushing
   toward expensive places. Both are registered: the districts where they *disagree* are the
   informative ones.
3. **Safety broadened from crime to physical risk.** Added traffic fatalities (NHTSA FARS)
   and overdose and firearm mortality (CDC WONDER). These come from crash records and death
   certificates, so coverage is near-complete exactly where FBI voluntary reporting has
   gaps. Road deaths especially: per-capita rates run several times higher in rural counties
   and frequently exceed the absolute risk difference from crime. Safety indicators: 2 → 5.
4. **Offline-first build.** The data hosts are still blocked, so Phase 1 was built and
   tested against synthetic fixtures. This is better engineering regardless — the tests do
   not break when census.gov is down — and it is the same code either way.

### 2026-08-22 — Universe includes census designated places (GOAL.md amendment)
`GOAL.md` said "every **incorporated** place above ~5,000 people", which taken literally
excludes CDPs — unincorporated communities, many of them perfectly good places to live.
That would be a systematic coverage bias against exactly the kind of overlooked place this
project exists to surface: it matched the charter's wording while cutting against its
intent. **Amended** the mission wording to cover incorporated municipalities and census
designated places alike. Expected universe: ~5,000 places becomes ~7,000–8,000.

**Scope also fixed at 50 states + DC.** Puerto Rico's 78 municipios and the island areas
are deliberately excluded for now — see Open Question #8, so the choice stays visible
rather than becoming an accident of implementation.

### 2026-08-22 — Two registry errors caught while building
Recorded because both would have been near-invisible later:

- **`form_population` was sourced to the Census Gazetteer, which contains no population at
  all.** Gazetteer files carry geography only. Re-sourced to ACS (`B01003_001E`), along with
  `form_population_density`, whose numerator is ACS and whose denominator is Gazetteer land
  area held on the universe table.
- **A symmetric band shoulder scored a 500-person village 0.51 on a 25,000–250,000
  population band**, because 24,500 reads as "close" in linear units. Population is
  effectively logarithmic. Added optional `shoulder_lo`/`shoulder_hi` to `ideal_band` and
  gave population a tight lower shoulder; the village now scores 0.00 and a 20,000-person
  town gets partial credit at 0.38.

---

## Data inventory

Nothing ingested yet — Phase 0 built no pipeline by design. `docs/data-sources.md` holds
the full catalog with URLs, vintages, geography levels, and licenses. This table tracks
ingest state and is filled in during Phase 2.

| Source | Geo level | Vintage | Coverage | Status |
|---|---|---|---|---|
| census_gazetteer | county, place | 2024 | — | module written, **download blocked** |
| census_acs5 | county, place | 2020–2024 | — | module written, **download blocked** |
| fema_nri | county | 2023 | — | module written, **download blocked** |
| usda_amenities | county | 1999 | — | module written, **download blocked** |
| _(34 others)_ | | | | Phase 2 |

Concrete download URLs are pinned in `DOWNLOADS` in `src/wlm/cli.py`. **None have been
verified** — every host is denied by the egress policy, so `make data` is the first thing
that will actually resolve them. A moved URL gets corrected there and in
`docs/data-sources.md`, never worked around.

---

## Indicator registry status

| Metric | Count |
|---|---|
| Domains defined | 13 — 11 scoring, 2 questionnaire-only (`config/domains.yaml`) |
| Sources registered | 38 (`config/sources.yaml`) |
| Indicators registered | 50 (`config/indicators.yaml`) — expands to 60+ in Phase 2 |
| Indicators carrying provisional curve params | 11 — placeholders awaiting Phase 3 elicitation |
| Indicators with an ingest module written | 5 (ACS, FEMA NRI ×3, USDA amenities) |
| **Indicators populated with real data** | **0 — every host is still blocked** |

Validate with `make validate`; the invariants are enforced mechanically and the negative
cases are covered by `make test` (90 tests, none needing network).

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
7. **Territories.** Puerto Rico (78 municipios), USVI, Guam, American Samoa and the
   Northern Marianas are excluded — scope is 50 states + DC. Reconsider only if the
   household wants it; the geography code filters them at `wlm.geo.STATE_FIPS`.
8. **Crime data coverage.** FBI CDE reporting is agency-voluntary and patchy. Decide in
   Phase 2 whether to flag gaps, substitute a modeled estimate, or down-weight the safety
   domain where coverage is thin. Must not be silently imputed (Principle 6).

---

## Next actions

1. **Add the hostnames in `docs/network-allowlist.md`** to the environment's egress policy.
   This is now the only thing blocking real data — the pipeline is written and tested.
2. **Run `make data`, then `make universe`.** First real run resolves and pins the download
   URLs. Expect roughly 3,143 counties and 7,000–8,000 places; anything far off that is a
   bug, not a surprise.
3. **Phase 2 — Ingest:** expand to 60+ indicators. NOAA station→county aggregation is the
   known-fiddly one, deliberately deferred out of Phase 1.
4. **Capture current residence** at the earliest opportunity (Open Question #1) — still the
   highest-value missing fact.
