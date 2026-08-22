# Data sources — catalog

Every source is free, bulk-downloadable, authoritative, and versioned. **No source in this
catalog is a website to be read** — each is a file or API to be downloaded, checksummed,
and pinned (Principle 3).

**Vintage column** names the *target* release. Actual vintage is pinned at ingest and
recorded in `data/raw/MANIFEST.json` with a SHA-256. Phase 1 verifies every URL resolves
before scaling ingest; a URL that has moved gets corrected here, not worked around.

**License column**: `PD` = US Government public domain (17 U.S.C. §105), free to use.
Non-PD sources are flagged and carry attribution or non-commercial terms — noted per row.

---

## Geography — the universe

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| Census Gazetteer files | `census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html` | county, place | 2024 | PD |
| Census TIGER/Line | `www2.census.gov/geo/tiger/` | all | 2024 | PD |
| CBSA delineation files | `census.gov/geographies/reference-files/time-series/demo/metro-micro/delineation-files.html` | metro | 2023 | PD |

## Demographics and housing stock

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| ACS 5-year (API) | `api.census.gov/data/2024/acs/acs5` | county, place | 2020–2024 5-yr | PD |
| Census Building Permits Survey | `census.gov/construction/bps/` | county, metro | annual | PD |

## Cost of living

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| BEA Regional Price Parities | `apps.bea.gov/regional/downloadzip.htm` | metro, state | annual | PD |
| MIT Living Wage Calculator | `livingwage.mit.edu` | county | annual | Free w/ attribution |
| HUD Fair Market Rents | `huduser.gov/portal/datasets/fmr.html` | county, ZIP | FY2026 | PD |
| Zillow ZHVI / ZORI | `zillow.com/research/data/` | metro, city, ZIP | monthly | Free, non-commercial, attribution |
| FHFA House Price Index | `fhfa.gov/data/hpi` | metro, county | quarterly | PD |

## Jobs and economy

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| BLS QCEW (employment, wages by industry) | `bls.gov/cew/downloadable-data-files.htm` | county | annual | PD |
| BLS LAUS (unemployment) | `bls.gov/lau/` | county, metro | monthly | PD |
| BLS OES (occupational wages) | `bls.gov/oes/tables.htm` | metro | annual | PD |
| BEA per-capita personal income | `apps.bea.gov/regional/downloadzip.htm` | county | annual | PD |

## Climate and environment

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| NOAA NCEI US Climate Normals | `ncei.noaa.gov/products/land-based-station/us-climate-normals` | station → county | 1991–2020 | PD |
| **FEMA National Risk Index** | `hazards.fema.gov/nri/data-resources` | county, tract | 2023 | PD |
| EPA AQS annual summaries | `aqs.epa.gov/aqsweb/airdata/download_files.html` | monitor → county | annual | PD |
| USDA ERS Natural Amenities Scale | `ers.usda.gov/data-products/natural-amenities-scale` | county | 1999 | PD |

> **FEMA NRI is the decisive source for the Florida/Texas question.** It quantifies 18
> hazards — hurricane, tornado, wildfire, riverine and coastal flooding, heat wave,
> drought, earthquake — as expected annual loss, so hazard exposure becomes a scored
> number rather than a vibe. The USDA Natural Amenities Scale is a genuine 1999 index of
> climate, topography, and water area; it is old but structural (mountains do not move)
> and is used for terrain, not for anything time-varying.

## Health

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| County Health Rankings (RWJF) | `countyhealthrankings.org/health-data` | county | annual | Free w/ citation |
| HRSA shortage areas (HPSA) | `data.hrsa.gov` | county, sub-county | current | PD |
| CMS hospital quality | `data.cms.gov/provider-data/` | facility → county | annual | PD |

## Safety — physical risk, not crime alone

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| FBI Crime Data Explorer | `cde.ucr.cjis.gov` | agency → county | annual | PD |
| CDC WONDER mortality | `wonder.cdc.gov` | county | 2023 | PD |
| NHTSA FARS crash fatalities | `nhtsa.gov/file-downloads` | county | 2023 | PD |

> **Why this domain is broader than crime.** FBI reporting is voluntary and the NIBRS
> transition left real gaps — some states have poor agency participation. CDC WONDER and
> FARS are built from death certificates and crash records, so their coverage is close to
> complete exactly where FBI data has holes.
>
> It also measures the right thing. Per-capita **road fatality** rates run several times
> higher in rural counties than in dense metros and frequently exceed the absolute risk
> difference from crime — a factor almost no relocation research counts. Overdose and
> firearm mortality are included on the same reasoning.
>
> **Caveats, both flagged rather than imputed (Principle 6):** FBI agency gaps, and CDC
> WONDER's suppression of county-year cells with fewer than 10 deaths — which bites hardest
> in small counties, so it must not be read as "safe." See `CONTEXT.md` Open Question #7.

## Education

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| **Stanford Education Data Archive (SEDA)** | `edopportunity.org/get-the-data/` | district | v5.0 | Free w/ citation |
| NCES Common Core of Data | `nces.ed.gov/ccd/` | district, school | annual | PD |
| NCES EDGE district relationship files | `nces.ed.gov/programs/edge/` | district → county | 2024 | PD |
| Urban Institute Education Data API | `educationdata.urban.org` | district, school | annual | Free w/ attribution |

> **SEDA is the reason this domain is trustworthy.** It publishes *learning rates* — how
> much students improve per grade — alongside raw achievement levels.
>
> Scoring schools on raw test scores is the standard approach and it is close to useless
> here: district proficiency correlates heavily with local family income, so a raw-score
> ranking largely measures how wealthy the neighbours are and calls it school quality. It
> would also collide with the cost domain, quietly pushing the ranking toward expensive
> places. Growth measures what the schools do rather than who attends them.
>
> Both are registered as separate indicators, because districts where they *disagree* are
> the informative ones — low scores with high growth is a very different bet from the
> reverse.
>
> **Geography note:** school districts do not nest inside counties or places. NCES EDGE
> relationship files carry SEDA's district values onto the universe; the indicator registry
> records this explicitly via `crosswalk_from`.

## Family and childcare

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| DOL National Database of Childcare Prices | `dol.gov/agencies/wb/topics/childcare/price-by-age-care-setting` | county | 2022 | PD |

## Air connectivity to Europe

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| BTS international air segments | `data.transportation.gov/resource/xgub-n9bw.json` | US airport → county | 2024 | PD |
| OpenFlights airport coordinates | `raw.githubusercontent.com/jpatokal/openflights` | airport | current | ODbL, attribution |

> **Why this exists.** The household has family in Europe and reads "cheap access to
> Europe" as implying the east coast. That is an inference, not a fact — transatlantic
> nonstops also run from Denver, Dallas, Houston, Phoenix, Chicago, Minneapolis and
> Seattle. Encoding "east coast" as a preference would smuggle in an assumption; measuring
> **nonstop European destinations from the nearest hub, and the drive to reach it**, lets
> the ranking test it instead.
>
> Europe is world area codes **400–499** in the BTS scheme (Copenhagen 419, Paris 427,
> Frankfurt 429, Dublin 441, Amsterdam 461, Madrid 482, London 493). Istanbul is 679 and
> correctly falls outside.

## Connectivity and amenities

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| FCC National Broadband Map | `broadbandmap.fcc.gov` | block → county | biannual | PD |
| BTS T-100 / airport data | `transtats.bts.gov` | airport | monthly | PD |
| FTA National Transit Database | `transit.dot.gov/ntd` | agency, metro | annual | PD |
| **County Business Patterns** | `www2.census.gov/programs-surveys/cbp/datasets/` | county | 2022 | PD |
| ~~OpenStreetMap via Overpass~~ | `overpass-api.de` | — | — | **egress-blocked, replaced by CBP** |

> **OSM is the amenity workhorse.** Counts of groceries, gyms, parks, libraries,
> trailheads, clinics, places of worship, and third places, computed per capita within a
> radius. It is the only source that covers small places as thoroughly as large ones,
> which makes it a direct countermeasure to coverage bias.

## Taxes and utilities

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| Tax Foundation state tables | `taxfoundation.org/data/` | state | annual | CC BY-NC |
| Census property tax (ACS B25103) | `api.census.gov` | county, place | 2020–2024 5-yr | PD |
| EIA electricity prices | `eia.gov/electricity/data.php` | state, utility | monthly | PD |

## Sensitive — ingested, shipped at weight 0

Per Principle 10 and the 2026-08-22 decision. Stored as **direction-neutral raw
indicators**; the household's preference curve decides direction, the registry assumes none.

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| MIT Election Lab county returns | `dataverse.harvard.edu` (MEDSL) | county | 2000–2024 | CC0 |
| ARDA US Religion Census | `thearda.com` | county | 2020 | Free w/ registration + citation |
| ACS ancestry, foreign-born, language | `api.census.gov` | county, place | 2020–2024 5-yr | PD |
| State policy indices | compiled, cited per index | state | current | varies |

## Hype index — diagnostic only, never an input

| Source | URL | Geo | Vintage | License |
|---|---|---|---|---|
| IRS SOI migration data | `irs.gov/statistics/soi-tax-stats-migration-data` | county | annual | PD |
| Census county-to-county flows | `census.gov/topics/population/migration/data.html` | county | 5-yr | PD |
| Zillow price appreciation | derived from ZHVI above | metro, ZIP | monthly | see Zillow row |

---

## Adding a source

1. Add a row here with URL, geography level, target vintage, and license.
2. Write `src/wlm/ingest/<source>.py` emitting the common long form:
   `geo_level | geo_id | indicator_id | value | vintage | source_file`.
3. Register each indicator it produces in `config/indicators.yaml`.
4. Record the download in `data/raw/MANIFEST.json` with a SHA-256.

Steps 1 and 4 are not optional — scoring refuses to run against an unmanifested file.
