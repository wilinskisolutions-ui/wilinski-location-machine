"""The single download path. Every byte the pipeline consumes comes through here.

Behaviour that matters:

- **Resumable.** A file already manifested with a matching checksum is not re-downloaded,
  so `make data` is safe to re-run and cheap when nothing changed.
- **Atomic.** Downloads land in a temp file and are renamed only on success, so an
  interrupted run can never leave a truncated file that looks complete.
- **Loud.** An unreachable host raises, naming the host and the path it expected. Absence
  is always visible — a silent skip would let a place score on missing data.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from wlm.manifest import Manifest, sha256_file
from wlm.paths import RAW

DEFAULT_TIMEOUT = 120


class FetchError(RuntimeError):
    """A source could not be retrieved. Carries the host so the cause is obvious."""

    def __init__(self, url: str, expected: Path, reason: str):
        self.url = url
        self.host = urlparse(url).netloc
        self.expected = expected
        self.reason = reason
        super().__init__(
            f"could not fetch {url}\n"
            f"  host:     {self.host}\n"
            f"  reason:   {reason}\n"
            f"  expected: {expected}\n"
            f"If the host is blocked by the egress policy, see docs/network-allowlist.md."
        )


def _filename_for(url: str) -> str:
    name = Path(urlparse(url).path).name
    return name or "download"


def fetch(
    source_id: str,
    url: str,
    *,
    filename: str | None = None,
    root: Path = RAW,
    manifest: Manifest | None = None,
    offline: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    vintage: str | None = None,
    force: bool = False,
) -> Path:
    """Download `url` for `source_id`, record it, and return the local path.

    Set `offline=True` to require that the file already exists — used by tests and by any
    run that must not touch the network.
    """
    own_manifest = manifest is None
    manifest = manifest or Manifest.load()

    dest_dir = root / source_id
    dest = dest_dir / (filename or _filename_for(url))
    rel = dest.relative_to(root).as_posix()

    # Already have it, intact? Nothing to do.
    if not force and manifest.verify(rel, root):
        return dest

    if dest.exists() and (entry := manifest.get(rel)) and sha256_file(dest) != entry.sha256:
        raise FetchError(
            url, dest, "file on disk does not match its recorded checksum — delete it to re-download"
        )

    if offline:
        raise FetchError(url, dest, "offline mode and the file is not present")

    try:
        import requests
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise FetchError(url, dest, f"requests is not installed ({exc})") from exc

    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    try:
        with requests.get(url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            with tmp.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    if chunk:
                        fh.write(chunk)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise FetchError(url, dest, f"{type(exc).__name__}: {exc}") from exc

    tmp.replace(dest)
    manifest.record(source_id=source_id, url=url, file=dest, root=root, vintage=vintage)
    if own_manifest:
        manifest.save()
    return dest


def register_fixture(
    source_id: str,
    fixture: Path,
    *,
    root: Path,
    manifest: Manifest,
    url: str = "fixture://synthetic",
    note: str = "synthetic fixture - shape only, values fabricated",
) -> Path:
    """Place a fixture into a raw-data root, marked synthetic.

    This is how the pipeline is exercised with the network blocked. The `synthetic: true`
    flag it writes is what `Manifest.assert_no_synthetic` later refuses to score.
    """
    dest_dir = root / source_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / fixture.name
    dest.write_bytes(fixture.read_bytes())
    manifest.record(
        source_id=source_id, url=url, file=dest, root=root, synthetic=True, note=note
    )
    return dest


def proxy_status() -> str:
    """One-line description of the egress setup, for error reporting."""
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    return f"HTTPS_PROXY={proxy}" if proxy else "no HTTPS_PROXY set"
