PY := PYTHONPATH=src python3
PYTEST := PYTHONPATH=src:tests python3

.PHONY: help validate test demo data universe features score diagnostics report \
	audit calibrate coverage questionnaire clean

help:
	@echo "validate     Check config registries against the GOAL.md principles"
	@echo "test         Run the test suite"
	@echo "demo         Run the built stages on synthetic fixtures (no network needed)"
	@echo "coverage     Report what has data and what does not, with reasons"
	@echo ""
	@echo "questionnaire            Run it locally.  PERSON=practice|emil|winsor  RESET=1"
	@echo "calibrate    Check the elicited weights against places they already know"
	@echo "audit        Check the system against the ten principles in GOAL.md"
	@echo "data         Download + checksum all sources (needs network - see docs/network-allowlist.md)"
	@echo "universe     Build the fixed candidate universe          [Phase 1]"
	@echo "features     Join, transform, percentile-rank            [Phase 2]"
	@echo "score        Apply curves, weights, knockouts, rank bands"
	@echo "diagnostics  Hype residual, coverage, sensitivity        [Phase 4]"
	@echo "report       Build the ranked report - refuses any rank without its band"

validate:
	@$(PY) -m wlm.config.validate

test:
	@$(PYTEST) -m unittest discover -s tests

PERSON ?= practice
RESET ?=

questionnaire:
	@$(PY) -m wlm.questionnaire.server --person $(PERSON) $(if $(RESET),--reset,)

audit:
	@$(PY) -m wlm.diagnostics.audit

calibrate:
	@$(PY) -m wlm.diagnostics.calibration

coverage:
	@$(PY) -m wlm.diagnostics.coverage

data universe features score diagnostics report demo:
	@$(PY) -m wlm.cli $@

clean:
	rm -rf data/interim/* data/processed/* output/* 2>/dev/null || true
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
