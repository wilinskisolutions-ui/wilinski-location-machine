# Test fixtures — SYNTHETIC DATA

**Every file in this directory contains fabricated values.** They exist so the pipeline can
be built and tested while the data hosts are blocked by the egress policy.

They encode **shape only** — column names, delimiters, FIPS padding, the quirks of each
real format. The numbers are invented and mean nothing.

## Why they cannot leak into a result

`GOAL.md` Principle 4 says no LLM supplies a number. That is enforced structurally, not by
convention:

1. Fixtures live here and are never written to `data/raw/` by the real pipeline.
2. `wlm.fetch.register_fixture` marks every entry it creates `synthetic: true` in the manifest.
3. `Manifest.assert_no_synthetic` raises `SyntheticDataError` if any scoring stage sees one,
   naming the offending file.
4. `tests/test_synthetic_guard.py` asserts that refusal actually fires.

## Cases deliberately covered

`gazetteer_places.txt` and `place_county_crosswalk.csv` between them exercise: an ordinary
incorporated place, a census designated place, a place below the 5,000 floor, a place
spanning two counties, a place with no population figure, a place with no county match,
and a Puerto Rico row that must be filtered as out of scope.
