# CONTEXT — living state

> **Session protocol.** Read `GOAL.md` first, then this file, then act. Update this file
> before ending any session in which something was decided, learned, or built. This file
> is the project's working memory: a session that reads it should be able to resume cold
> without re-deriving anything or re-asking a settled question.

**Current phase:** Phase 2 — Real data · **Status:** Tier 1 complete on real downloads;
9,885-place universe built, 23 indicators populated
**Blocking Phase 3:** the questionnaire, plus the household's calibration ratings
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
| **Current residence** | **Harrisburg, PA** — place `4232800` (pop 50,649), Dauphin County `42043` (pop 293,029), Harrisburg–Carlisle metro. Verified against Census files. |
| Baseline role | **Baseline only.** Scored and used as the reference, excluded from candidates — they are definitely leaving. |
| Push factors | **Climate/weather** and **things to do, culture, food.** Built first and deepest. |
| Geographic pull | No hard constraint. Warm preferred; family in Europe, which they read as implying the east coast. |
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

### 2026-08-22 — Phase 2: real data, and five corrections it forced
Network opened; 21 of 26 sources verified by live probe. Tier 1 (the household's stated
priorities) built end to end. Five things the real data changed:

1. **The Census API now requires a key** (`X-DataWebAPI-KeyError`). Pivoted entirely to
   keyless bulk files, which suits Principle 3 better anyway — bulk files are versioned and
   checksummable; an API is a moving target.
2. **PEP contains no CDPs.** 19,465 of its 19,479 place rows are active incorporated, so
   the decision to include census designated places would have silently failed. Place
   population now comes from the ACS bulk table (32,325 place rows) for *all* places, one
   vintage, so vintage never correlates with place class. Counties use PEP 2024.
3. **Connecticut has no counties.** It replaced them with nine planning regions in 2022;
   the 2020 place-codes file names the old ones, the 2024 Gazetteer carries the new. 216
   lookups failed, which would have dropped Connecticut entirely. Fixed with a general
   nearest-centroid fallback rather than a CT special case, and counted in the build report.
4. **Geometric county centroids bias climate.** Dauphin's sits 7.5 miles north of its
   population centroid, in higher ground, reading ~3F colder than Harrisburg itself.
   Switched to Census population-weighted centroids: climate should be measured where
   people live.
5. **FEMA's headline risk score is population-confounded.** `RISK_SCORE` ranks expected
   annual *loss*, which scales with how much property exists — Los Angeles scores 100
   partly for being Los Angeles. Used raw it penalises populous counties, fighting this
   household's amenity preference for reasons unrelated to safety. Added
   `hazard_fatality_risk_per100k` from expected annual loss of life over population. The
   two nearly invert: Gallatin MT is 81st percentile on FEMA's composite but carries **5x
   Miami-Dade's per-capita fatality risk**; Manhattan looks risky and is the safest per
   person.

### 2026-08-22 — The east-coast assumption, measured
The household reads "cheap access to Europe" as implying the east coast. Built as a
measurement rather than a preference. Result: **40 US airports have European nonstops**,
including Chicago (34 destinations), Atlanta (28), **Austin (23)**, Detroit (22),
Charlotte (19), Dallas (17), Denver (16), Minneapolis (15), Seattle (14), Houston (13).
Austin beats Charlotte, Denver and Dallas. The east-coast constraint is measurably weaker
than assumed.

Hub selection is **best reachable within 200 miles**, not nearest: from Harrisburg, Dulles
is 22 miles further than Baltimore and offers 66 European destinations against 18. Picking
"nearest" would have understated every place sitting between two hubs.

**And the finding that cuts hardest: Harrisburg already ranks 92nd percentile for European
access and 14th percentile for per-capita hazard risk.** It is already safe and already
well connected. Most warmer places will be worse on both — the move has to be justified on
climate and amenities, which is what the household said was driving it.

### 2026-08-22 — Preliminary signal (NOT a ranking)
A crude four-condition filter — warmer than Harrisburg, more restaurants, more arts venues,
lower per-capita hazard risk, population over 100k — leaves **26 of 3,143 counties**.
States: NY 5, VA 5, CA 4, GA 3, NC 1, MA 1, CO 1, OR 1, NM 1, WV 1. **No Florida, no Texas,
no South Carolina, no Tennessee** — the Sunbelt corridor does not survive its own hazard
numbers. Equal implicit weights, 23 indicators, no elicited preferences: indicative only.
Real scoring is Phase 4.

---

## Data inventory

Nothing ingested yet — Phase 0 built no pipeline by design. `docs/data-sources.md` holds
the full catalog with URLs, vintages, geography levels, and licenses. This table tracks
ingest state and is filled in during Phase 2.

| Source | Geo level | Vintage | Coverage | Status |
|---|---|---|---|---|
| census_gazetteer | county, place | 2024 | 100% | **ingested** |
| census_acs5 (bulk B01003) | county, place | 2019–2023 | 100% | **ingested** — the only CDP population source |
| census_pep | county, place | 2024 | 100% | **ingested** |
| census_place_codes / cenpop | place / county | 2020 | 100% | **ingested** — crosswalk + centroids |
| noaa_normals | county | 1991–2020 | 3,142/3,144 | **ingested** — 15,616 stations |
| census_cbp | county | 2022 | 3,045 | **ingested** — replaces blocked Overpass |
| bts_intl + openflights | county | 2024 | 100% | **ingested** — 40 transatlantic hubs |
| fema_nri (ArcGIS) | county | 2023 | 100% | **ingested** — static host is WAF-blocked |
| bls_qcew, bea_rpp, epa_aqs, chr_rwjf, zillow, nhtsa_fars | — | — | — | downloaded, **ingest modules pending (Tier 2)** |
| _(remaining)_ | | | | Phase 2 continuation |

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
| Indicators registered | 68 (`config/indicators.yaml`) |
| Indicators carrying provisional curve params | 11 — placeholders awaiting Phase 3 elicitation |
| Indicators with an ingest module written | 23 |
| **Indicators populated with real data** | **23** — climate 8, hazard 7, amenities 5, air 3 |
| Universe | **9,885** — 3,144 counties + 6,741 places (4,811 incorporated, 1,930 CDP) |

Validate with `make validate`; the invariants are enforced mechanically and the negative
cases are covered by `make test` (90 tests, none needing network).

---

## Open questions and known unknowns

1. **Where does the household currently live?** The single highest-value missing fact.
   For a domestic move it sets the baseline every candidate is scored against, it anchors
   the calibration set, and it determines what "better" even means. First question of the
   Phase 3 questionnaire; ask sooner if the chance arises.
2. **Preferred names and pronouns** — see the 2026-08-22 decision above.
2b. **Climate is measured at county level**, so a county average differs from the specific
   town: Dauphin reads 32.4F winter against Harrisburg station's 34.7F. Acceptable for
   Phase 2, but climate is a top-weighted domain — consider place-centroid weighting in
   Phase 4.
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

1. **Finish Tier 2 ingest.** Files are downloaded and manifested; modules still needed for
   `bls_qcew`, `bea_rpp`, `epa_aqs`, `chr_rwjf`, `zillow_research`, `nhtsa_fars`. Each is a
   reader plus a column map against the existing `emit` contract.
2. **Resolve the two unreachable sources.** SEDA's download links are JS-gated (needs one
   manual download registered into the manifest); HUD FMR returns 202 with zero bytes —
   Zillow ZORI covers rent meanwhile.
3. **Get the household's calibration ratings** — 15–20 places they know, rated 1–10,
   including Harrisburg. Without it no ranking is trustworthy, and it is the cheapest thing
   left to collect.
4. **Phase 3 — Questionnaire.** Weights by forced trade-off; both partners independently.
