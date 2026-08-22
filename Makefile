PY := PYTHONPATH=src python3

.PHONY: help validate test data universe features score diagnostics report clean

help:
	@echo "validate     Check config registries against the GOAL.md principles"
	@echo "test         Run the test suite"
	@echo "data         Download + checksum all sources (needs network - see docs/network-allowlist.md)"
	@echo "universe     Build the fixed candidate universe          [Phase 1]"
	@echo "features     Join, transform, percentile-rank            [Phase 2]"
	@echo "score        Apply curves, weights, knockouts            [Phase 4]"
	@echo "diagnostics  Hype residual, coverage, sensitivity        [Phase 4]"
	@echo "report       Build the ranked HTML report                [Phase 4]"

validate:
	@$(PY) -m wlm.config.validate

test:
	@$(PY) -m unittest discover -s tests

data universe features score diagnostics report:
	@$(PY) -m wlm.cli $@

clean:
	rm -rf data/interim/* data/processed/* output/* 2>/dev/null || true
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
