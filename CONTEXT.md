# CONTEXT — living state

> **Session protocol.** Read `GOAL.md` first, then this file, then act. Update this file
> before ending any session in which something was decided, learned, or built. This file
> is the project's working memory: a session that reads it should be able to resume cold
> without re-deriving anything or re-asking a settled question.

**Current phase:** Phase 4 complete; atlas built; **the website (web/) built, accounts ready to switch on.** An interactive
map (`make atlas`, published at `https://claude.ai/artifact/Y4oyTiP8Xoa6LNQdDaoQeU`) puts the
household's own wishlist next to the machine's live challengers, every town scored the same way
under joint weights the couple set together on the map. All 10 GOAL.md principles pass;
**56 of 66 indicators populated.** A fresh clone now rebuilds from scratch: `make data` fetches
the four API sources it used to skip.
**Still open:** Winsor's questionnaire answers, and `profiles/emil.yaml` is not in the repo (it
was never committed; Emil's budget split survives only in the 2026-08-23 entry below).
**Last updated:** 2026-10-17

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
| Work situation | **Income fully portable** (2026-10-15). Local jobs start at weight 0 on the atlas. |
| Budget | **Rent first, then buy.** Rent ceiling **$2,000/month** (2026-10-15). Purchase budget not yet given. |
| Timeline | Exploring areas in person through **September 2027** (2026-10-15). |
| Children | **None, none planned** (2026-10-15). Schools and childcare start at weight 0. |
| Pets | Unknown |
| Stated leaning | Describes the household as "more conservative"; explicitly not ready to turn this into a filter |
| Non-negotiables | None captured yet |
| Wishlist (2026-10-15) | Washington DC suburbs, Boston, Franklin TN (with Nashville), St. Augustine FL, Sarasota FL. Treated as places to *test*, not candidates — see the atlas entry. |
| Lifestyle factors named (2026-10-15) | Church community, walkable downtown and food, water and nature, airport access to Europe. |

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

**And a ninth, of a kind worth naming separately: a test whose premise had quietly become
false.** `test_dataless_domain_raises_a_named_warning` weighted `education` and asserted the
"cannot affect this ranking" warning fired. It passed for as long as education had no data,
and the moment education was filled it started failing — correctly. The test was borrowing
a condition from the world rather than constructing one, so it had been describing a state
of affairs rather than guarding a behaviour. It now drops a domain's indicators from the
frame deliberately, and a companion test asserts the warning does *not* fire for a domain
that does have data — without which the first check cannot fail meaningfully. **Filling a
gap can break a test that was only ever true by accident, and that failure is information.**

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

### 2026-08-23 — Emil answered for real, and it found the deepest bug yet

Emil filled out the phone questionnaire and exported his answers. Landing them and running
the actual pipeline — the step the page itself cannot do — surfaced two real bugs, one of
them structural to the elicitation method itself, not to any one household's data.

**1. Amenity density had no population floor, and the top of Emil's ranking was Great
Plains counties of a few thousand people.** `amen_arts_rec_per10k` and its siblings are
establishment counts per 10,000 residents; a county of 4,051 people with four arts venues
produces a wildly inflated rate purely from the tiny denominator. `census_cbp.py` already
carried a comment naming this exact risk (San Juan County, CO) and had registered
`amen_arts_rec_total`/`amen_food_drink_total` as the intended counterbalance — but those
totals were never added to the trade-off attribute list in `bank.yaml`, so they could never
earn more than the 0.05 floor weight while the per-capita version reached 0.22 in Emil's fit.
The documented mitigation existed in the registry and did nothing in practice.

Fixed with a population floor on the rate's denominator (`MIN_POPULATION_FOR_RATE = 10_000`
in `census_cbp.py`), the same treatment `fars.py` already gives road-fatality rates. Below
the floor, the rate cannot exceed the raw establishment count — verified as an exact
equality, since 10,000 is also the "per 10k" scale factor. The new top of the distribution
is Jackson Hole WY, Aspen (Pitkin County CO), Breckenridge (Summit County CO), Manhattan:
real amenity-dense places, not statistical noise. Legitimate small tourism counties (Custer
County ID, 4,597 people, 19 genuine venues as the Sawtooths gateway) are still allowed to
rank — the floor caps the multiplier, not the finding.

**2. The trade-off fit was unregularized, and the informativeness check read the wrong
number — both found only because a real household finally exercised this path.** Two
compounding problems:

- `fit_choices` ran unpenalized logistic regression over ~15 design attributes against
  ~24-28 real choices (p/n ≈ 0.6). Emil's real answers hit in-sample accuracy of exactly
  1.00, and his second-highest revealed weight (`amen_arts_rec_per10k`, 0.22) had a
  **negative** coefficient — his choices looked like a preference against culture and
  recreation venues, which is almost certainly collinearity with cost in the specific pairs
  he saw rather than a real aversion. Added L2 regularization (`l2=0.3`, tested from 0.05 to
  3.0 against his real data — 0.3 was the smallest penalty that reached a stable accuracy
  plateau without flattening every coefficient toward uniform importance).
- `is_informative` gated on **in-sample** accuracy at a 0.65 threshold. Measured against the
  real bank design: pure random answers produced in-sample accuracy averaging 0.83-0.95
  across trials — the check was passing almost regardless of whether the choices meant
  anything. Replaced with leave-one-out cross-validated accuracy (`_leave_one_out_accuracy`
  in `elicit.py`), which cannot be inflated by the model's own capacity because each
  held-out choice was never used to fit the model being tested against it.

**The CV threshold itself needed calibrating, not guessing — LOO accuracy is a noisy
estimator at this n.** A first attempt at 0.6 let 3 of 6 fresh random trials through as
"informative." Sixty trials of pure noise on the real design gave a mean of 0.50 (std 0.12,
p95 = 0.68); sixty trials of a coherent synthetic respondent gave a median of 0.68 — the two
distributions overlap substantially at ~25 choices over ~15 attributes, and no threshold
cleanly separates them. Set to **0.68** deliberately favouring the safe failure mode: a
false negative falls back to the household's own directly stated budget allocation, already
a fully legitimate path; a false positive corrupts the ranking with revealed weights that
only look like findings. That asymmetry, not a belief that 0.68 is uniquely correct, decided
the number.

**Consequence for Emil specifically.** His trade-off choices came out at cv_accuracy=0.542 —
not informative. His weights are his stated 100-point budget allocation exactly (cost,
climate, urban_form, career all 12; safety and health_care 10; the rest 8), not a blend with
a noisy fit. His ranking changed materially between the two runs: the amenity fix alone
still left Great Plains/Appalachian small towns dominant because the elicitation was still
overweighting the miscalibrated arts_rec signal; with both fixes his real top is Harrisonburg
and Staunton, VA — real Shenandoah Valley cities, "somewhat warmer" than Harrisburg per his
own anchored answers, with strong healthcare access and social capital. Report republished.

**Two structural findings worth carrying forward**, not specific to Emil:
- Every future respondent sits in the same p/n≈0.6 regime this analysis was run against, so
  the fix generalises rather than being tuned to one household's answers.
- At ~24-28 choices, roughly half of genuinely consistent respondents will still fall back
  to stated-allocation-only under the 0.68 threshold. That is an accepted, documented
  trade-off (see the threshold rationale in `elicit.py`), not a remaining bug — but if the
  trade-off block is ever revisited, more tasks or fewer simultaneous attributes per task
  would let more real signal clear the bar without loosening the noise threshold.

`tests/test_elicitation_reliability.py` (new, 7 tests) pins both fixes and the calibration
reasoning as regression guards. Full suite still green; `make audit` still 10/10.

---

### 2026-10-15 — The atlas: a map over the evidence, and the wishlist put to the test

The household asked for "a futuristic, interactive map of the United States" to manage a year
of exploring — Washington DC's suburbs, Boston, Franklin TN, St. Augustine and Sarasota — with
each place zooming into its towns, and research on which make sense financially and for safety.

**The tension, stated up front.** That list is two Florida towns and a Nashville suburb: the
exact shape GOAL.md names as the internet's retrieval bias, and the 2026-08-22 preliminary
filter found no Florida or Tennessee county surviving its own hazard numbers. Principle 1 says
nothing enters the universe because it came up in conversation. **Resolution:** the wishlist does
not enter the universe — every one of those places is already in it. A pin is a *view*: a radius
around an existing place, scored identically to every other town. And the map always shows the
machine's challengers beside the picks, so the wishlist is tested rather than trusted.

**Decisions taken by the household (multiple-choice, 2026-10-15):**

| Question | Answer | Consequence |
|---|---|---|
| Relationship to the machine | Wishlist + machine picks | Challengers recomputed live, `engine.two_stage` in miniature |
| Zoom depth | Towns + ZIP prices | Census place outlines + Zillow ZIP rents (ZCTA) |
| Housing | Rent first, then buy | Rent drives the budget flag; ZHVI shown for later |
| Income | Fully portable | `jobs` factor starts at 0 |
| Children | None, none planned | `schools` factor starts at 0 |
| Rent ceiling | Under $2,000/mo | Flag, never a silent removal: over-budget towns stay visible, red |
| Lifestyle factors | Church, downtown & food, water & nature, Europe airport | Religious adherence **opted in** (Principle 10), higher-is-better by their stated direction |
| Scoring until Winsor answers | **Set joint weights together now** | See the amendment below |

**Principle 8 amendment (atlas only).** The household chose one shared 100-point split, set
together on the map, over separate scoring. Old rule: each partner scored separately, conflict
surfaced. New rule *for the atlas*: one joint weight vector, stored in the page's shared store.
The engine's `joint()` and the questionnaire are untouched, so separate scoring remains available
the moment Winsor's answers exist. Reason: they want one map to plan trips from, now.

**How it is built — and why it cannot drift from the engine.**
- `config/atlas.yaml` regroups every registered indicator into 13 factors (rent & cost, safety,
  hurricane & hazard, climate, downtown & food, water & nature, church community, health, Europe
  flights, community, town size, jobs, schools). The build refuses to run if an indicator is
  placed twice, or nowhere without an exclusion reason.
- Per-factor scores come from `engine.domain_scores` — a new split of `engine.score` into its
  within-domain half and `engine.combine_domains`. The page recombines with the household's
  weights in `score.js`, and `tests/test_atlas.py` holds it to `combine_domains` over 400 random
  cases, holds its formatter to `wlm.units.fmt`, and its ring decoder to the Python encoder.
- Town rent = land-area-weighted Zillow ZORI over the ZIPs overlapping the town (Census 2020
  ZCTA-to-place relationship file), required to cover at least 25% of the town's land; otherwise
  the county figure stands in, labelled. 5,070 of 6,741 towns get a town-level rent.
- Outlines: Census cartographic boundary files, simplified per zoom, one lazy-loaded file per state.

**What the data said on the first run (default weights, $2,000 cap):**

| Area | Best town (fit) | Its rent | Towns under cap |
|---|---|---|---|
| Washington DC & suburbs | Manassas (56) | $2,229 | 47 of 216 |
| Boston area | Franklin Town (40) | $2,663 | 0 of 68 |
| Franklin & Nashville | Brentwood (49) | $2,068 | 4 of 11 |
| St. Augustine | Fruit Cove (46) | $2,032 | 2 of 8 |
| Sarasota | Sarasota Springs (42) | $2,002 | 6 of 25 |
| Top challenger | Lynchburg, VA (65) | $1,268 | — |
| Home | Harrisburg, PA (50) | $1,375 | — |

Every picked area's best-fitting town is over the cap; Boston has no town under it at all.
Sarasota city scores 0.11 on hurricane and hazard. The top challenger — Lynchburg, Shenandoah
side of Virginia — is in the same corridor Emil's own ranking found on 2026-08-23.

**Four repairs made on the way:**

1. **A fresh clone could not build features.** BTS, FEMA NRI, CDC and the Urban Institute school
   data were fetched by hand in earlier sessions and never manifested, so `make features` died on
   the first missing JSON. `wlm.ingest.api_sources` now fetches them in `make data`, through each
   module's own reader, with checksums.
2. **The Zillow reader inherited stale prices.** Its docstring promised a suppressed market would
   "stay missing rather than inherit a stale 2019 price"; `_latest` walked back to 2000. Now capped
   at 12 months, with a test.
3. **The USDA amenities scale was never ingested for real** — only the demo fixture existed.
   The ERS workbook is now downloaded and read, and its water-area component is registered as
   `env_water_area_share` (66 indicators; 56 populated).
4. **`engine.score` split** into `domain_scores` + `combine_domains`, behaviour unchanged (full
   suite green), so the atlas reuses the engine instead of reimplementing it.

**Known limits, stated rather than hidden.** Climate still scores against the provisional
40-62°F winter band, not an elicited one. Crime is still absent from safety. ZIP rents exist only
where Zillow publishes (8,459 ZIPs). The shared store makes the page organization-internal:
Winsor needs access to the claude.ai organization to open it.

---

### 2026-10-17 — The atlas becomes a website for other households

The household's partner asked for it: "make this into a workable website that people can
make an account to, put in their preferences and explore." Decided by multiple choice:

| Question | Answer |
|---|---|
| What is it | **Donation-funded hobby** for now; a payment wall only if costs grow |
| Account wall | **After the wizard**: anyone can set up and see their map; sign up to save it |
| Accounts | **Single or couple**: a couple shares one map and one set of weights, each with their own login |
| Sensitive layers | **Keep as opt-in sliders**, against the advice to drop them for the public |
| Supabase | The household's own account, for sign-in and saved maps |

**GOAL.md amended** (anti-goals): "not a product for anyone else" removed. Old: a
general-purpose database *or a product for anyone else*. New: not a general-purpose
database. Reason: the household chose to offer it. Every principle still applies to each
visitor: their universe is the same fixed one, their weights come from a 100-point budget,
sensitive layers are off until they turn them on.

**What was built (branch `claude/atlas-web`, stacked on the atlas PR):**
- `web/`: a Vite app. Seven-step wizard (who, home town, money, life, winters, weights
  with opt-in sensitive layers, top picks); the map from the atlas, now driven by each
  visitor's settings; saved to the browser until sign-up, then to Supabase.
- Scoring stays the engine's. `config/atlas.yaml` gains a `web` section: public starting
  weights, five **winter presets** re-scored through `engine.domain_scores` (the wizard
  asks "colder, same or warmer than where you live now"), and three **sensitive layers**
  whose direction the visitor picks: higher is the engine's percentile, lower its
  complement, "close to even" the engine's `ideal_point` on the raw margin
  (`score.js idealPoint`, held to `curves.ideal_point` by test).
- The household's own `church` factor is marked `household_only` and is not offered.
- `web/supabase/migrations/0001_init.sql`: households (one or two members), settings,
  pins, notes, one-time invites; row-level security on every table; functions for
  creating a map, inviting and joining a partner, deleting an account.
- `.github/workflows/web.yml`: builds the data, runs every test, builds the site, and
  deploys to Cloudflare Pages on `main` once the secrets exist; monthly for fresh prices.

**Verified, not assumed:**
- The RLS migration ran on a throwaway Postgres 16 as four people (`make test-db`):
  a stranger sees nothing and cannot write, an invite works once, a full couple takes
  nobody else, a partner keeps the map when the other deletes their account. Mutation
  check: with the pins policy opened to everyone, the run fails at the stranger check.
- The wizard-to-map flow, driven in Chromium at desktop and phone sizes: pins and notes
  survive a reload, moving a weight re-ranks the challengers, no console errors, no
  sideways scroll.
- Found and fixed on the way: a hidden modal swallowing every click (the artifact
  wrapper had been supplying the `[hidden]` rule); one partner's account deletion would
  have cascaded away the couple's shared map; a member could rewrite `created_by`;
  `roundTo100` returning 96 for inputs not already summing to 100; two climate steps
  mapping to the same preset; factor descriptions written for this household only.

**Not yet verified:** a live Supabase project (needs the household's project URL and
anon key), Google sign-in, and realtime sync between two phones.

**Standing risks, recorded so they are decided once:**
- Fair housing: steering by religion or national origin is illegal; the layers are opt-in,
  visitor-directed and never hide a place. A fair-housing lawyer's read is required before
  the site is opened beyond friends and family.
- Zillow's terms: recorded as non-commercial with attribution; verify before any payment
  wall. HUD Small Area FMRs are the public-domain fallback.
- Focus: Wilinski Solutions is in its advertising phase. The household's time on this is
  review only.

**2026-10-17, later: the migration failed on the real Supabase project.** The household
ran it and reported "doesn't work"; a read-only probe with the anon key showed none of
the six tables existed. Cause, reproduced locally once the test stub was made to behave
like Supabase: invite tokens used `gen_random_bytes`, which lives in Supabase's separate
`extensions` schema, so the one-transaction script failed at line 80 and created nothing.
The bare-Postgres stub had hidden it. Fixed by using the built-in `gen_random_uuid()`.
The stricter stub also exposed a second problem the old one could not see: Supabase grants
every new table to `anon` and `authenticated`, so the column-level grant on `households`
did nothing there; privileges are now revoked first and granted back one by one. The
script is idempotent (safe to re-run after a failure) and the harness applies it twice.
Mutation check: dropping the revoke makes the run fail.

Also learned: Supabase's built-in email only delivers to the project's team members, at
about 2 an hour, so strangers cannot sign up until a custom SMTP sender is configured; the
site now says so in plain words. Google sign-in is off in the project, so its button is
hidden until it is switched on (read live from the project's public settings).

Hosting: the household chose **Netlify**. The workflow deploys there with the Netlify CLI;
the project URL and anon key live in `web/.env.production` (public by design). A race was
fixed where the wizard closed before the new map was drawn (the browser test caught it
once accounts were configured). The artifact preview is now its own build: a classic
script, no account code.

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

### 2026-10-17 — Questions a person can answer, and weights that bite

Emil read his ranking and said three things: it looks the same every time, the questions
are strange ("you're asking me to choose between different concentrations of a gas in the
air"), and he is not sure the weather part worked. All three were correct, and each was
measured before anything was changed.

**1. Two trade-off attributes were genuinely unanswerable, and the generator had no
contrast rule at all.** It drew two random places and displayed whatever fell out, so he
was asked to choose between "3.8 and 8.5 micrograms per cubic metre" and "7.6 against 9.5
arts venues per 10,000". Fixed: indicators now declare `phrasing`, ten carry a phrase
ladder keyed to national percentile, and every shown attribute must separate the two places
by at least 25 percentile points and two phrase rungs. One rung produced "on a big lake or
the coast" against "substantial water" — technically different, reads the same. The pool is
cut from seventeen to ten; `env_pm25_annual` and `hazard_fatality_risk_per100k` are retired
from elicitation and still measured and scored.

**2. The trade-off block could never have estimated weights, at any pool size.** It fits
one free parameter per attribute from twenty-five choices. A design sweep over the real data
fitted a simulated respondent with three strong, coherent preferences against pure random
answers, at every pool size from eight to seventeen:

| Attributes | Coherent (median LOO) | Random (95th pct) | Separation |
|---|---|---|---|
| 8 | 0.700 | 0.748 | −0.048 |
| 9 | 0.700 | 0.680 | +0.020 |
| 10 | 0.680 | 0.640 | +0.040 |
| 17 | 0.620 | 0.640 | −0.020 |

Separation is zero everywhere. So `elicit.agreement` now **checks** his stated weights
against his choices instead: no free parameters, an ordinary binomial test, real power at
n=25. **On his actual answers it returns 54% of 24 choices, p=0.42** — his almost-flat
allocation does not predict his choices better than a coin. That is a finding about the
weights, now printed on the page instead of averaged away in silence.

*Recorded because it was nearly shipped as a finding:* an earlier run of this check
reported 75% at p=0.011 for him. `choice_tasks` is seeded, so regenerating after the
question rewrite produces `choice_7` showing a **different pair** — that run compared his
answers against questions he never saw. Replayed answers are only meaningful against the
exact question set that produced them, which is also why his twenty-five choice answers
were dropped rather than carried forward.

**3. Weight and influence had come apart, inverted.** A domain's pull on the ranking is
`weight × spread(log domain score)`, and that spread falls out of indicator count rather
than anything the household chose. Climate carried the joint-highest weight across sixteen
overlapping measures and came **seventh of ten** on influence, below family_childcare at
eight points across two. Fixed with `engine.influence_scale` plus eight redundant
indicators retired; influence now tracks weight at r=0.9999 with climate first. `score.js`
applies the same factors so the atlas page ranks by the same rule.

**4. `scoring: false` was read by nothing.** Found while doing (3).
`env_natural_amenities` carried a registry note saying it was excluded so his climate
preference would not be counted twice — and it was being scored anyway. Now enforced in
`attach_desirability`, the one place every ranking passes through.

**5. The USDA reader hardcoded its header row** (104) in a file whose first hundred rows
are prose someone edits. It searches for the header now, and also reads column 11, which
gives `env_topographic_variation` — the mountains-and-scenery half of the "nature, beauty"
Emil asked for, alongside the water share. Spot-checked: Sierra Nevada and Mogollon
counties at 21, Mississippi Delta counties at 1, Nantucket and San Francisco Bay at 75%
water.

**6. A concrete town-size question** replaces "Harrisburg's county has 290,886 people,
somewhat more or somewhat less?" — a five-point scale against a quantity spanning five
orders of magnitude, which he answered "don't care either way".

**Also:** Virginia independent cities labelled in the report as city-units, since
Harrisonburg competes at 17 square miles against counties with a national median of 616 ·
band floors clamped to the indicator's physical minimum ("much less snow" was producing a
band starting at −19 inches) · `openpyxl` added to the pipeline extra, which `src` imports
in three places and a fresh clone could not run without.

**Lost and rebuilt.** A container reclaim took the whole working tree before any of this
was committed, along with 707MB of source data and Emil's uploaded answers. The data was
re-downloaded from `MANIFEST.json`, the code rewritten onto the restructured engine the
atlas branch left behind, and his answers reconstructed from the conversation. The lesson
is cheap to apply: **commit each coherent piece as soon as it is written**, not after
verification.

**Open, and Emil's call:** his housing ceiling of $450k removes 283 counties and the
three-hour airport limit removes **1,403** — nearly half the country, pointing hard at the
mid-Atlantic. Both are real preferences, not bugs, but the size of the second is worth
seeing before he re-answers.


## Next actions

00. **Switch on accounts** (project `dvcqgoligcixiegyhnol`, keys already in the repo):
    re-run the fixed `web/supabase/migrations/0001_init.sql` in the SQL editor, deploy to
    Netlify, put the Netlify address in Supabase's URL Configuration, and set up a custom
    SMTP sender before inviting anyone outside the Supabase team. Steps in `web/README.md`.

0. **Use the atlas together** — `https://claude.ai/artifact/Y4oyTiP8Xoa6LNQdDaoQeU`. Set the
   joint weights first (the Weights tab), then plan visits: for every two wishlist areas, one
   challenger. Rebuild with `make atlas` and republish `output/atlas/index.html` after any data
   or config change. Tell us the real winter-temperature band to replace the placeholder.

0. **Emil re-answers the trade-off block — 35 questions, not the whole thing.** His 21
   still-valid answers are carried forward onto the rebuilt question set. The 25 choice
   answers were **dropped, not reused**: `choice_tasks` is seeded, so `choice_7` still
   exists but now shows a different pair, and reusing the old answer scores one question
   against another (see the 2026-10-17 entry — that mistake produced a spurious 75%).
1. **Then both answer in full.** Two routes, same questions:
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

**Published artifacts** — republish the same *file path*, passing the URL, to update in
place rather than creating a second copy:

| What | File | URL |
|---|---|---|
| Emil's questionnaire | `output/questionnaire-emil.html` | `https://claude.ai/artifact/NFQTWRCRpFEVJ1yD5uqTKT` |
| Winsor's questionnaire | `output/questionnaire-winsor.html` | `https://claude.ai/artifact/GeLpVK2vxqrBqUoLyMCfQC` |
| Practice run | `output/questionnaire-practice.html` | `https://claude.ai/artifact/4im6aFp43NrdM2gimwbiUF` |
| Emil's ranking | `output/report-emil.html` | `https://claude.ai/artifact/GnSJrzCW1inbZafdRSrncS` |

**Live reweighting lives in the atlas, not the questionnaire.** A questionnaire-side weights
screen that re-ranked a baked-in shortlist as the points moved was built and then lost with
a container; `make atlas` already does the same thing better, over a map, with the same
`combine_domains` arithmetic. Rebuilding it in the questionnaire would mean two half-versions
of one idea, so the published questionnaire pages carry no preview and the atlas is the
answer to "what happens if I move the points".

**Phase 4 is built.** Scoring, two-stage ranking, rank bands, the report and all four
anti-bias diagnostics run end to end. `make audit` reports 10 of 10. The earlier placeholder-weights report (`cb7c443a-…`) is superseded by the table above.
