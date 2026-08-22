"""Pipeline entry point.

Phase 0 ships the stage structure without the stages. Each unimplemented stage exits
cleanly naming its phase and what it will produce, so `make universe` tells you where the
project is rather than raising a traceback.

Stages: universe -> ingest -> features -> scoring -> diagnostics -> report
(docs/methodology.md section 9)
"""

from __future__ import annotations

import sys

STAGES: dict[str, tuple[int, str]] = {
    "data":        (1, "download + checksum every source into data/raw/ with a MANIFEST.json entry"),
    "universe":    (1, "enumerate counties and places from Census geography -> data/processed/universe.parquet"),
    "features":    (2, "join to universe, apply transforms, compute national percentiles -> data/processed/features.parquet"),
    "score":       (4, "apply curves, weights, aggregation and knockouts -> data/processed/scores.parquet"),
    "diagnostics": (4, "hype residual, coverage, weight sensitivity, political with/without -> output/"),
    "report":      (4, "ranked HTML with per-place explanations -> output/report.html"),
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in STAGES:
        print(f"usage: python -m wlm.cli <{'|'.join(STAGES)}>", file=sys.stderr)
        return 2

    stage = argv[0]
    phase, description = STAGES[stage]
    print(f"stage '{stage}' is not implemented yet — scheduled for Phase {phase}.")
    print(f"  will: {description}")
    print("\nPhase 0 (charter) is complete. See CONTEXT.md 'Next actions' for what unblocks this.")
    if stage == "data":
        print("Note: this environment's egress policy currently blocks the data hosts.")
        print("      See docs/network-allowlist.md.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
