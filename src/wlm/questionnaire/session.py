"""Questionnaire session state: save, resume, reset — and the practice-mode guarantee.

Emil wants a practice run before the real thing. That only works if a practice session is
**structurally incapable** of touching a real profile, rather than merely unlikely to.
`REAL_PEOPLE` is an allowlist, and `Session.finish` refuses to write a profile for any name
outside it. A typo cannot overwrite real answers.

Answers are written after every question, so a closed laptop loses nothing and a
45-minute sitting can be split.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from wlm.paths import ROOT

PROFILES = ROOT / "profiles"
SESSIONS = PROFILES / ".sessions"

# The only names that may ever produce a real profile file.
REAL_PEOPLE = ("emil", "winsor")
PRACTICE = "practice"

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class SessionError(ValueError):
    """A session was addressed with a name or state that is not allowed."""


def normalize_person(name: str) -> str:
    """Lower-case and validate a person name, rejecting anything path-like."""
    person = (name or "").strip().lower()
    if not NAME_PATTERN.match(person):
        raise SessionError(
            f"invalid person name {name!r}; use letters, digits and underscore only"
        )
    if person not in REAL_PEOPLE and person != PRACTICE:
        raise SessionError(
            f"unknown person {person!r}; expected one of {', '.join(REAL_PEOPLE)} or '{PRACTICE}'"
        )
    return person


def is_practice(person: str) -> bool:
    return person == PRACTICE


@dataclass
class Session:
    person: str
    answers: dict[str, object] = field(default_factory=dict)
    position: int = 0
    started_at: str = ""
    finished_at: str | None = None
    sessions_dir: Path = SESSIONS

    # ------------------------------------------------------------------ lifecycle

    @property
    def path(self) -> Path:
        return self.sessions_dir / f"{self.person}.json"

    @classmethod
    def load(cls, person: str, *, sessions_dir: Path = SESSIONS) -> Session:
        person = normalize_person(person)
        path = sessions_dir / f"{person}.json"
        if path.exists():
            raw = json.loads(path.read_text())
            return cls(
                person=person,
                answers=raw.get("answers", {}),
                position=raw.get("position", 0),
                started_at=raw.get("started_at", ""),
                finished_at=raw.get("finished_at"),
                sessions_dir=sessions_dir,
            )
        return cls(
            person=person,
            started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            sessions_dir=sessions_dir,
        )

    def save(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "person": self.person,
            "answers": self.answers,
            "position": self.position,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(self.path)

    def reset(self) -> None:
        """Discard everything and start clean."""
        self.answers.clear()
        self.position = 0
        self.finished_at = None
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.path.unlink(missing_ok=True)

    # ------------------------------------------------------------------- answers

    def record(self, question_id: str, value: object) -> None:
        self.answers[question_id] = value
        self.save()

    @property
    def answered(self) -> int:
        return len(self.answers)

    # -------------------------------------------------------------------- output

    def profile_path(self) -> Path:
        if is_practice(self.person):
            raise SessionError(
                "practice sessions do not write a profile — that is the point of practice mode"
            )
        return PROFILES / f"{self.person}.yaml"

    def can_write_profile(self) -> bool:
        return self.person in REAL_PEOPLE

    def finish(self) -> Path | None:
        """Mark complete. Returns the profile path, or None for a practice run."""
        self.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.save()
        return self.profile_path() if self.can_write_profile() else None


def completed_people(sessions_dir: Path = SESSIONS) -> list[str]:
    """Which real people have finished. Used to keep results hidden until both are done."""
    done = []
    for person in REAL_PEOPLE:
        path = sessions_dir / f"{person}.json"
        if path.exists() and json.loads(path.read_text()).get("finished_at"):
            done.append(person)
    return done


def both_finished(sessions_dir: Path = SESSIONS) -> bool:
    """Independence rule: no one sees anyone's results until both have answered."""
    return len(completed_people(sessions_dir)) == len(REAL_PEOPLE)
