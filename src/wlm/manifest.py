"""Provenance record for every downloaded file.

`GOAL.md` Principle 3 — every number traces to a source file with a URL, vintage and
checksum — is enforced here rather than remembered. Nothing enters the pipeline without a
manifest entry.

Principle 4 — no LLM supplies a number — is enforced by the `synthetic` flag. Phase 1 is
built against fixtures, so fabricated values exist in the repo; `assert_no_synthetic` makes
them structurally incapable of reaching a real result.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from wlm.paths import MANIFEST, RAW

SCHEMA_VERSION = 1


class SyntheticDataError(RuntimeError):
    """Raised when synthetic input would reach a real result. Never catch this."""


class ChecksumError(RuntimeError):
    """A file on disk does not match the checksum recorded for it."""


@dataclass(frozen=True)
class Entry:
    source_id: str
    url: str
    path: str  # POSIX, relative to data/raw
    retrieved_at: str
    sha256: str
    bytes: int
    synthetic: bool = False
    vintage: str | None = None
    note: str | None = None

    @property
    def is_placeholder(self) -> bool:
        """True when this entry stands in for a real download."""
        return self.synthetic


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Manifest:
    entries: dict[str, Entry] = field(default_factory=dict)  # keyed by relative path
    path: Path = MANIFEST

    # ---------- persistence ----------

    @classmethod
    def load(cls, path: Path = MANIFEST) -> Manifest:
        if not path.exists():
            return cls(entries={}, path=path)
        raw = json.loads(path.read_text())
        entries = {e["path"]: Entry(**e) for e in raw.get("entries", [])}
        return cls(entries=entries, path=path)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "updated_at": now_iso(),
            "entries": [asdict(e) for e in sorted(self.entries.values(), key=lambda e: e.path)],
        }
        # Write via a temp file so an interrupted save cannot truncate the manifest.
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n")
        tmp.replace(self.path)

    # ---------- recording ----------

    def record(
        self,
        *,
        source_id: str,
        url: str,
        file: Path,
        root: Path = RAW,
        synthetic: bool = False,
        vintage: str | None = None,
        note: str | None = None,
    ) -> Entry:
        rel = file.relative_to(root).as_posix()
        entry = Entry(
            source_id=source_id,
            url=url,
            path=rel,
            retrieved_at=now_iso(),
            sha256=sha256_file(file),
            bytes=file.stat().st_size,
            synthetic=synthetic,
            vintage=vintage,
            note=note,
        )
        self.entries[rel] = entry
        return entry

    def get(self, rel_path: str) -> Entry | None:
        return self.entries.get(rel_path)

    # ---------- verification ----------

    def verify(self, rel_path: str, root: Path = RAW) -> bool:
        """True when the recorded file exists and still matches its checksum."""
        entry = self.entries.get(rel_path)
        if entry is None:
            return False
        f = root / rel_path
        return f.exists() and sha256_file(f) == entry.sha256

    def verify_all(self, root: Path = RAW) -> list[str]:
        """Return the paths whose files are missing or altered."""
        return [rel for rel in self.entries if not self.verify(rel, root)]

    # ---------- the guardrail ----------

    def synthetic_entries(self) -> list[Entry]:
        return [e for e in self.entries.values() if e.synthetic]

    def assert_no_synthetic(self, context: str = "this stage") -> None:
        """Refuse to proceed if any input is fabricated.

        Fixture data exists so the pipeline can be built and tested with the network
        blocked. It must never reach a ranking the household would act on.
        """
        bad = self.synthetic_entries()
        if not bad:
            return
        listed = "\n".join(f"  - {e.path}  (source: {e.source_id})" for e in bad)
        raise SyntheticDataError(
            f"{context} refuses to run: {len(bad)} input(s) are synthetic fixtures, "
            f"not real downloads.\n{listed}\n\n"
            "GOAL.md Principle 4: no LLM supplies a number. Run `make data` against the "
            "real sources first (see docs/network-allowlist.md)."
        )
