# CONTEXT — living state

> **Session protocol.** Read `GOAL.md` first, then this file, then act. Update this file
> before ending any session in which something was decided, learned, or built. This file
> is the project's working memory: a session that reads it should be able to resume cold
> without re-deriving anything or re-asking a settled question.

**Current phase:** Phase 4 — Scoring · **Status:** complete. Engine, two-stage ranking, rank
bands, report and all four anti-bias diagnostics run end to end. **All 10 GOAL.md principles
pass** (`output/audit.md`). **54 of 65 indicators populated; no scoring domain is empty.**
Four bug sweeps so far; each found bugs in a path nothing had exercised, and the rate is
not yet falling.
**Blocking a real ranking:** two completed profiles. Everything in `output/` was produced
from placeholder weights and says so on its face.
**Answering:** the questionnaire now also runs as a phone artifact, one page per person.
**Last updated:** 2026-08-23

---

## Household facts

The accumulating record of who this is being built for. Most of it is captured by the
Phase 3 questionnaire; anything already known is recorded here so it is never re-asked.

| Field | Value |
|---|---|
| Members | **Emil** and **Winsor** *(pronouns not stated for either — use names)* |
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

### 2026-08-22 — Phase 2 complete: Tier 2 ingest, and four more corrections
Populated indicators 23 → **44 of 64**. Every remaining gap has a named reason in
`output/coverage.md` (new `make coverage` target), which is now the answer to "what is
missing" instead of that living in anyone's head.

New readers: `chr_rwjf` (one CSV covering health, providers, parks, social capital and
unemployment), `census_acs` derived indicators (8, several cross-table ratios), `zillow`
(county files), `epa_aqs`, `fars`, `bls_qcew`, `bea_rpp`, `cdc_mortality`.

Four corrections the data forced:

1. **Zillow publishes county files.** Using them instead of the metro files removed the
   need for a CBSA crosswalk on housing entirely.
2. **CHR's provider measure is the reciprocal of ours.** It publishes physicians per head;
   the registry asks for people per physician, which is what `lower_better` means for that
   indicator. Left alone the direction would have been exactly backwards.
3. **Per-capita rates explode in tiny counties.** Places carry a 5,000 floor; counties do
   not. Loving County, Texas (~64 residents) showed **6,250 road deaths per 100,000** — two
   orders of magnitude above anywhere else, purely from the denominator, and mostly
   pass-through highway traffic. Rates now require a population of at least 1,000; 36
   counties fall below it and are left missing.
4. **CDC suppression works differently than assumed.** Counts are *binned* (`1-9`,
   `10-50`) but rates are published anyway, and zero-rate rows carry genuine zeros. Checked
   rather than guessed, so the rates are used rather than needlessly discarded.

**Known universe gap:** five places with population ≥5,000 (largest 53,043, four in
Massachusetts) exist in ACS 2019–2023 but are absent from the 2024 Gazetteer — a vintage
mismatch in geography, not a join bug. 0.07% of places; revisit if the Gazetteer vintage
moves.

**Air-quality coverage is thin by nature:** only 637 of 3,144 counties have a PM2.5
monitor. Left missing rather than interpolated, so it lowers coverage instead of inventing
clean air for unmonitored places.

### 2026-08-22 — Phase 3: questionnaire built, and the design flaw Emil caught
Emil's objection, verbatim: *"A question like 'Do you prefer high homicide rates?' doesn't
make sense to ask an actual human, because obviously everyone would answer no."* He was
right, and it reshaped the instrument.

**The fix:** every indicator now carries `direction: universal | personal` (49 universal,
15 personal). A universal direction — crime, life expectancy, air quality, hazard — means
there is no preference to elicit, only a **trade-off weight**. Direction questions are
reserved for the 15 where the ideal genuinely differs: town size, winter temperature,
density, rootedness, the sensitive layer. `tests/test_questionnaire.py` enforces it, so it
cannot creep back as the bank grows.

**How weights are actually measured now:** 28 place-vs-place choices drawn from real rows in
`features.parquet`. Two unnamed places, neither better on everything, pick one. Fitting a
logistic utility over the attribute differences recovers weights from *behaviour* rather
than self-report — which is the only way to measure something like air quality, where
asking directly is absurd. Verified against synthetic data with known weights: the fit
recovers the ordering, and near-random answers are reported as uninformative rather than
dressed up as findings. Because the places are unnamed, this doubles as countermeasure #5,
blind evaluation.

**Anchored on Harrisburg.** All 10 band questions read "compared with here", with real
values filled in (winter 32°F, snow 26", population 50,092, median age 32). Absolute
numbers are hard to answer honestly; comparisons to home are easy.

**Runs locally, at Emil's request** — `make questionnaire`, loopback only, nothing uploaded.
Practice mode is enforced by an allowlist rather than by care: a practice session is
*structurally incapable* of writing `emil.yaml` or `winsor.yaml`. Reset and resume both work;
answers save after every question.

**Independence on one shared laptop:** sessions are per-person files, no cross-display, and
results stay hidden until both have finished.

**Two bugs caught while building:** four band questions were silently dropping because their
indicators are place-level and the baseline lookup only read county level — those four
would have kept my provisional guesses. And the older validator fixtures had to be updated
once `direction` became mandatory, which is the validator doing its job.

### 2026-08-22 — Logic audit: seven bugs, two of which corrupted the weights
Emil asked whether the questions, data and machinery actually hold together. They did not.
Every finding below was reproduced against live data before being fixed.

| # | Bug | Why it mattered | Fix |
|---|---|---|---|
| 1 | **5 of 11 domains had no trade-off attributes** — career, education, family, community, sensitive | Their revealed weight was structurally 0, and the 65/35 blend cut whatever the household *said* about them to ~35%. The instrument could not hear them on schools or jobs. | Added career and community attributes; `blend()` now keeps uncovered domains at their stated weight and renormalises. |
| 2 | **Attribute count inflated domain weight** (sum, not mean) | A respondent valuing *everything equally* produced climate 30.8 vs healthcare 7.8 — a **4× spread measuring my questionnaire design, not their values**. | Domain weight is the mean of its indicator weights. Spread fell to 1.25×, which is sampling noise. |
| 3 | **Percentage anchors parsed at the wrong scale** | `profile.py` read the baseline out of the *display string*: "79%" became 79.0 on data running 0–1, putting the band outside the distribution. **0 places matched; the indicator was silently dead.** | Carry `anchor_value` (raw float). Band now spans 0.80–0.86 with 1,798 places inside. *Never parse back out of something formatted for humans.* |
| 4 | Duplicate rent indicator (`cost_rent_median`, never populated) | Inflated the cost domain's indicator count, feeding bug 2. | Retired; ZORI measures the same thing and has data. |
| 5 | Two domains carry no data at all | Weight on education or childcare evaporated on renormalisation, silently. | Scoring emits a named warning: *"education carries 18 points but has no data and cannot affect this ranking."* |
| 6 | Counties (~35 indicators) and places (~8) would rank together | A shallow place could win on near-perfect coverage of very little. | Two-stage: counties first, then places within the winners. |
| 7 | Calibration ignored `ideal_band` curves | A town of exactly the right size looked mediocre in the one check meant to validate everything. | Uses the real `desirability()`. |

**Two more found by building the engine**, not predicted:

- **Sparse candidates ranked high.** King County, Texas (population 215) placed 7th while
  scored on 48% of the weight. Added an 80% weight-coverage floor; exclusions are counted,
  not silent.
- **Per-capita amenity density measures tourism, not choice.** San Juan County CO
  (population 821, Silverton) shows **158 restaurants per 10k against Manhattan's 57**.
  Added absolute-variety indicators (`amen_food_drink_total`, `amen_arts_rec_total`,
  log-transformed) so density and variety are asked separately — they are different
  questions.

**And one the end-to-end test caught by itself**, which is the point of having it: a couple
asking for 50–70°F winters got places averaging 48°F, because `climate_environment` holds
sixteen indicators and a bare domain weight dilutes winter to about 1/16. The trade-off fit
already produced indicator-level weights; they were never wired into scoring. Now they are —
the same couple gets 51.6°F.

### 2026-08-22 — Scoring engine built (Phase 4 core)
`src/wlm/scoring/engine.py`: desirability via the real curves, weighted **geometric** mean
within then across domains (so one catastrophic domain cannot be averaged away), coverage
renormalisation, knockouts as an inspectable mask reporting what each removed, `worst_domain`,
two-person joint score with an explicit disagreement column, and Dirichlet sensitivity bands.

**Audit result: 9 of 10 principles pass** (`make audit`). Principle 9 is PARTIAL — sensitivity
is computed but no report emits it alongside a ranking yet. That must be wired before any
shortlist is shown, or a rank would be presented without its uncertainty.

### 2026-08-22 — Start screen: category explanations and an adjustable weight editor
Emil asked for two things: a way to adjust category weights later, and a few lines per
category explaining what it contains, because "urban_form" and "health_care" would stop
meaning anything once he had forgotten the details.

**Descriptions rewritten** from one-liners to 55–75 words each, naming the actual sources
and numbers, and — importantly — **what is still missing** from each. Education says out
loud that it is empty pending SEDA; safety says FBI crime data is absent and why.

**Weight editor** on the start screen, reachable any time from any question. Writes back to
`config/domains.yaml` by editing lines in place rather than re-dumping the file, so the
comments explaining each weight survive. Rejects any total that is not 100.

**The `locked` flag** is the honest part. Principle 7 says weights come from forced
trade-offs, so a hand-set weight is an override of the charter. Locking one keeps it through
elicitation *and records it in the profile as hand-set* — the difference between an explicit
override and a silent one.

**A misunderstanding worth recording:** Emil read "climate is 4× safety" from my bug report
and disagreed. The 4× was the *bug* (climate 30.8 vs healthcare 7.8 from attribute-count
inflation), since fixed. The actual placeholder ratio is 1.4×. Demonstrated that weights do
drive the answer — moving safety from 10 to 20 and climate from 14 to 4 changed 3 of the top
5 counties.

### 2026-08-22 — Second bug sweep: four more, found by running rather than reading
Emil asked whether the program actually works. Running it end to end found four bugs the
test suite had not, because each sat in a path nothing exercised.

| # | Bug | How it hid |
|---|---|---|
| 1 | **`make universe` was broken.** It picked the ACS population file with `glob("*.dat")` and took the first match. Adding the eight Tier 2 ACS tables silently changed that to `b25077` (home values), so the build failed on a missing population column. | `universe.parquet` on disk had been built *before* those tables landed, so every later stage kept working. A fresh clone would have failed immediately. |
| 2 | **Two-stage county→place ranking was never implemented.** I described it as done. `engine.py` had no place stage at all. | Nothing tested it, and the county ranking looked fine on its own. |
| 3 | **Sensitivity was unusably slow** — about 5 seconds a draw over all 3,144 counties, so the 200-draw default would have run ~17 minutes. | Only ever run with tiny draw counts. Now narrowed to the top 300 contenders: 50 draws in 29s, and nobody needs to know whether rank 2,000 is stable. |
| 4 | **Places were scored on place-level indicators alone**, so stage 2 returned **zero places**. The weights sit on climate, cost, safety and health — all county-level — so places were judged on almost nothing and dropped. | Only visible once stage 2 existed. `docs/methodology.md` had specified inheritance since Phase 0; I never implemented it. |

**And one structural finding.** 43% of US counties (1,359 of 3,144) contain no town above the
5,000 floor, and several were topping the ranking — Irion County, Texas, population 1,526,
ranked first. A county you cannot move to a town in is not a candidate for this decision, so
stage 2 now skips past them and says how many it skipped.

**System state after the sweep:** all eight `make` targets pass, 146 tests, 9,885 candidates,
46 indicators, 29 files checksummed, 0 synthetic. `make audit` still reports 9 of 10
principles passing — Principle 9 remains PARTIAL until sensitivity bands are emitted
alongside a ranking, which is now fast enough to actually do.

### 2026-08-23 — Third sweep: the browser, and the worst bug found so far

Driving the questionnaire in a real browser for the first time — Chromium via Playwright,
18 tests over the path Emil and Winsor will actually click — plus building the report and
diagnostics layers, turned up six bugs. Two of them broke charter principles outright.

**1. Principle 10 was broken in both directions, and the audit said PASS.**
The sensitive domain sits in the 100-point budget question like any other, so points
allocated to it flowed straight into the ranking **with no opt-in at all**. Meanwhile
opting in did nothing, because the answer was stored as option labels (`"Political
climate"`) that no code ever read. `make audit` reported the principle as passing
throughout, because the check only inspected the default weight in `config/domains.yaml` —
a check that could not fail on real behaviour.

Fixed structurally, not by remembering: `bank.yaml` declares which indicator each option
switches on (an unmapped option now raises); `build_profile` zeroes the domain weight and
redistributes it with a named note unless something was opted into; and `engine.score`
drops any sensitive indicator absent from that list. A zero weight would not have sufficed
— the within-domain floor keeps every indicator at 0.05, so silence has to mean absence.
The audit check now exercises the gate.

**2. 280 counties were scoring as the safest places in America because their data was
withheld.** CDC publishes suppressed death rates as the numeric sentinel **-999**, not as a
blank. `float("-999")` succeeded, so -999 entered the pipeline as a real rate on
`safety_firearm_death_rate` (180 counties) and `safety_overdose_death_rate` (100). Both are
`lower_better`. Missing data did not count as zero — **it counted as perfection**, which is
Principle 6 failing in the most damaging direction available.

Fixed at `ingest.base.emit`, the one gate every source passes through, rather than only in
the module that happened to hit it: a negative value on a unit that cannot be negative is a
publisher's flag, not a measurement. `degF`, `index` and `score` are excluded from the rule
— Fairbanks really is below zero. Rebuilt features: nulls rose 2,109 → 2,389, exactly the
280 rejected, and zero impossible negatives remain.

**The other four:**

| # | Bug | Consequence |
|---|---|---|
| 3 | A blank optional text box was recorded as `""` | A skipped question was indistinguishable from an answered one; clearing a box on the way back left the old value in place. |
| 4 | Zero scoreable candidates raised `ColumnNotFoundError` from polars | An opaque library error where the real answer is "no candidate has data in any weighted domain". Same pattern fixed in `sensitivity()`. |
| 5 | An unparseable knockout was skipped in silence | A deal-breaker could appear to be applied when it never ran. |
| 6 | Three copies of the unit formatter disagreed | Unemployment (0.003–0.17 in this data) was shown to Emil as **"0.0"** — a real figure rendered meaningless on the page meant to decide a move. Now one `wlm.units.fmt`, and four climate ids in the blind export were simply wrong, so the profiles carried no climate at all. |

**Method note.** Bugs 1, 3 and 6 were found by driving the real UI; bug 2 by auditing units
against their actual data ranges. Neither is something reading the code would have caught,
and both sweeps before this one found bugs at a similar rate. The rate is not yet falling.

---

### 2026-08-23 — The dead domains, the phone, and a fourth sweep

Emil asked for three things: answer on a phone, score education and political climate some
other way, and one more bug sweep.

**Education, childcare and the sensitive layer are no longer dead.** 46 of 65 indicators
populated became **54 of 65**, and *no scoring domain is empty any more*.

| Domain | Was | Now | Source |
|---|---|---|---|
| education | 0/6 | **4/6** | Urban Institute Education Data API — CCD directory, CCD finance, EDFacts graduation |
| family_childcare | 0/2 | **2/2** | DOL National Database of Childcare Prices |
| sensitive | 1/3 | **3/3** | county presidential returns (mirror), 2020 US Religion Census |

**The education numbers are substitutes, and the registry says so.** Phase 1 chose SEDA
*learning growth* because proficiency and spending largely measure how wealthy the
neighbours are. SEDA is still JavaScript-gated and Emil chose not to fetch it by hand, so
graduation rate, staffing ratio and spending stand in — each carrying `quality: substitute`
and a `quality_note` naming what it is weaker than. SEDA remains the documented upgrade.

**Two sources are behind sign-up forms and were routed around, not faked.** MIT's county
returns (`doi:10.7910/DVN/VOQCHQ`) need a Dataverse guestbook response; a long-standing
public mirror carries the same returns and is registered under its own source id with the
DOI recorded beside it. ARDA builds its archive pages client-side; the Religion Census
publishes the same tabulation directly as a workbook.

**Eight more bugs, every one caught by checking a number against something known.**

| # | Bug | The wrong number |
|---|---|---|
| 1 | Enrollment summed over all districts, teachers only over those reporting | Washoe County NV at **3,520 pupils per teacher** |
| 2 | A county graduation rate computed from whichever districts happened to file | Pima County, 1.08m people, **34% — from one school of 68 pupils** |
| 3 | Zero districts reported as 0 rather than missing | James City County VA ranked last on choice for a Virginia filing convention |
| 4 | EDFacts bins as wide as 0-49 treated as measurements | 603 midpoints that were arithmetic, not data |
| 5 | Alaska's House-district pseudo-FIPS collide with borough codes | **02020 is Anchorage Municipality and House District 20 at once** |
| 6 | A sheet column named "as % of Population" holds a 0-1 fraction | national religious adherence at a median of **0.5%** |
| 7 | Congregations counted where they sit, not where members live | King County TX at **452% adherence** of its 215 residents |
| 8 | A knockout question offering phrases mapped straight to a numeric threshold | "Under an hour" reached the engine as a string; **the deal-breaker never ran** |

Bug 8 is the one the sweep was for. Driving two complete profiles through the real HTTP API
— never done before — exercised `build_profile → write_profile → load_profile → score`,
`joint()`, calibration and knockouts for the first time. The fix follows the sensitive
opt-in pattern: the bank declares `option_values` next to the options it translates, and an
unmapped answer raises rather than being skipped.

**Also fixed:** calibration printed a "largest disagreements" table, with a paragraph on how
to read it, underneath "correlation unavailable" — presenting rank noise as a finding. It
now suppresses the table and says which of the two reasons applies.

**The phone.** `make questionnaire` still runs locally and is unchanged. Alongside it,
`wlm.questionnaire.artifact` bakes the 56 questions into a self-contained page, **one per
person** — that separation is Principle 8, since with the artifact capability a page's
markup *is* the shared document and one page for both would show Winsor what Emil picked.
Storage is layered: `localStorage` always, the artifact capability where granted, and a
`downloads` export as the escape hatch. Answers come back via
`artifact.answers_from_page()` and `artifact.land()`, which refuses practice for the same
reason `Session.finish` does. **The trade is real and was Emil's call:** answers stored this
way leave the laptop.

The first phone test found the page laying itself out at 980px and scaling down — the
artifact wrapper owns `<head>`, so the page now adds its own viewport meta.

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
| Sources registered | 47 (`config/sources.yaml`) |
| Indicators registered | 65 (`config/indicators.yaml`) |
| Indicators carrying provisional curve params | 14 — placeholders awaiting elicitation, per `make validate` |
| Ingest modules written | 18 |
| **Indicators populated with real data** | **54 of 65** — see `output/coverage.md` for the other 11; no scoring domain is empty |
| Universe | **9,885** — 3,144 counties + 6,741 places (4,811 incorporated, 1,930 CDP) |

Validate with `make validate`; the invariants are enforced mechanically and the negative
cases are covered by `make test`. Only the browser suite needs anything beyond the pipeline
extra — it drives real Chromium through Playwright, and skips itself when either is absent.

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

1. **Emil practises, then both answer.** Two routes, same 56 questions:
   * **Phone** — one published artifact per person, plus a practice page. Answers stay
     separate because the pages are separate.
   * **Laptop** — `make questionnaire PERSON=practice`, then `PERSON=emil`, then
     `PERSON=winsor`. See `questionnaire/HOW-TO-RUN.md`. Answers never leave the machine.

   ~45 minutes each. **Now safe to take.** Nothing else can proceed until this happens.
2. **`make calibrate`** — if the elicited weights do not reproduce their own ratings of
   places they know, the weights are wrong and no ranking should be trusted yet.
3. **Re-run the chain on real weights** once the profiles exist:
   `make score && make diagnostics && make report`. Everything currently in `output/` was
   produced from the placeholder weights and carries a banner saying so; all of it needs
   regenerating before any of it means anything.
4. **Optional data top-ups**, none blocking: education 0/6 (SEDA needs one manual download,
   its links being JS-gated), childcare 0/2, crime 2/5. `output/coverage.md` lists every gap.
   The sensitive layer is also 1/3 populated — partisan lean and religious adherence have no
   data — which only matters if it is ever opted into.

**Phase 4 is built.** Scoring, two-stage ranking, rank bands, the report and all four
anti-bias diagnostics run end to end. `make audit` reports 10 of 10. The demonstration
report is published at
`https://claude.ai/code/artifact/cb7c443a-4bc9-4405-89b4-d8c0849cb4bf` — republish the same
file path to update it in place rather than creating a second copy.
