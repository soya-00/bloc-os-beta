"""
The strip — the one record.

In air traffic control a flight strip carries a callsign, times and a status,
and moves between bays as the flight progresses. That is simultaneously a task,
a kanban card and an agenda block, seen from three angles. v0.1 had all three as
separate stores that could not talk: `t`/`l`/`c`/`d` operated on `inbox.md`, `k`
operated on `boards/*.md`, and there was no path between them — so the ATC
console, the best screen in the project, could not see board work at all.

The metaphor was right; the data model had not caught up. This module is the
data model catching up.

## Storage

One file per strip at `~/bloc/strips/BLK-041.md`: TOML frontmatter over a
Markdown body. Chosen over a single collection file for atomic per-record writes
— v0.1's `AgendaFile.save()` rewrote an entire day to tick one block — for clean
git history, and so a strip stays editable in any editor.

**Dates use TOML's own types.** Its offset-date-time, local-date and
local-date-time are exactly BLOC's three kinds of time, so `due` comes back a
`date`, `created` an aware `datetime` and `scheduled_start` a naive one, with
`formats.py` never involved. See `formats.py` for why the three are distinct.

## Identity

**The filename is the identity.** `next_id()` scans the directory and takes
`max + 1`, so there is no counter file to corrupt, desync or contend on — the
directory cannot disagree with itself about what exists. Numbers are never
reused: a callsign is a permanent name for a thing that happened, and reusing
`BLK-041` would silently repoint every reference to it.

## Status is not column

`status` is a closed five-value vocabulary the whole system understands.
`column` is free-form board position, invented by whoever made the board. A card
in a "Review" column is still `active`. Conflating them is what would make
boards and objectives disagree about the same strip.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from bloc.core import clock
from bloc.core.files import atomic_write_text, read_text
from bloc.core.formats import join_frontmatter, split_frontmatter
from bloc.core.vault import Vault

#: Callsign prefix and the shape `next_id()` produces.
PREFIX = "BLK"
ID_PATTERN = re.compile(rf"^{PREFIX}-(\d+)$")
ID_DIGITS = 3


class StripError(ValueError):
    """A strip document could not be understood."""


class Status(StrEnum):
    """
    Where a strip is. A `StrEnum` so a typo fails at the boundary instead of
    propagating as a string nothing matches — and so it still serialises to TOML
    as the plain word it looks like.
    """

    QUEUED = "queued"
    ACTIVE = "active"
    #: Blocked on someone else. Distinct from "not started yet", and the
    #: metaphor is exact: an aircraft in a hold is waiting for a clearance it
    #: has not been given.
    HOLDING = "holding"
    DONE = "done"
    #: Cancelled. Hidden from the bays but never unlinked — the vault is the
    #: record, and a deleted thing you cannot recover is data loss with a
    #: friendly name.
    SCRUBBED = "scrubbed"


#: The four bays, in order. `SCRUBBED` is deliberately absent.
BAY_ORDER: tuple[Status, ...] = (
    Status.QUEUED,
    Status.ACTIVE,
    Status.HOLDING,
    Status.DONE,
)

#: Statuses that still want something from you.
OPEN: frozenset[Status] = frozenset({Status.QUEUED, Status.ACTIVE, Status.HOLDING})


@dataclass(frozen=True)
class Strip:
    """
    One record. Frozen — transitions go through `replace()` or `with_status()`,
    so a strip is never half-updated.
    """

    id: str
    title: str
    status: Status = Status.QUEUED
    created: datetime | None = None

    due: date | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None

    board: str = ""
    column: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    priority: str = ""

    started: datetime | None = None
    completed: datetime | None = None

    body: str = ""

    # ── derived ───────────────────────────────────────────

    @property
    def is_open(self) -> bool:
        return self.status in OPEN

    @property
    def is_scheduled(self) -> bool:
        """A strip with a start time is also an agenda block."""
        return self.scheduled_start is not None

    def is_overdue(self, today: date | None = None) -> bool:
        """
        Past its due date and still wanted.

        A completed strip is never overdue however late it was — the question
        "what is pushing on me" has no useful answer that includes finished work.
        """
        if self.due is None or not self.is_open:
            return False
        return self.due < (today or clock.today())

    # ── transitions ───────────────────────────────────────

    def replace(self, **changes) -> Strip:
        return dataclasses.replace(self, **changes)

    def with_status(self, status: Status, now: datetime | None = None) -> Strip:
        """
        Move to a status, stamping the timestamp that move implies.

        The stamping lives here rather than in the caller because every caller
        would otherwise have to remember it, and the one that forgets produces a
        completed strip with no completion time — which quietly breaks every
        trend DEBRIEF is meant to draw.
        """
        now = now or clock.now()
        changes: dict = {"status": status}
        if status is Status.ACTIVE and self.started is None:
            changes["started"] = now
        elif status is Status.DONE and self.completed is None:
            changes["completed"] = now
        return self.replace(**changes)

    # ── serialisation ─────────────────────────────────────

    def to_document(self) -> str:
        """
        Render to frontmatter plus body.

        Empty and `None` fields are omitted rather than written as blanks: the
        file is meant to be readable and hand-editable, and a wall of empty keys
        is neither.
        """
        meta: dict = {"id": self.id, "title": self.title, "status": str(self.status)}
        if self.created:
            meta["created"] = self.created
        for name in ("due", "scheduled_start", "scheduled_end", "started", "completed"):
            value = getattr(self, name)
            if value is not None:
                meta[name] = value
        for name in ("board", "column", "priority"):
            value = getattr(self, name)
            if value:
                meta[name] = value
        if self.tags:
            meta["tags"] = list(self.tags)
        return join_frontmatter(meta, self.body)

    @classmethod
    def parse(cls, text: str, strip_id: str | None = None) -> Strip:
        """
        Read a strip document. Strict — raises `StripError` rather than guessing.

        Strictness is deliberate here and forgiveness lives one level up in
        `StripStore.all()`, which skips a bad file and records it. Guessing at
        this level would mean a corrupt strip silently becoming a *different*
        valid strip, which is worse than either.
        """
        meta, body = split_frontmatter(text)
        if not meta:
            raise StripError("no frontmatter — not a strip document")

        found = str(meta.get("id") or strip_id or "")
        if not ID_PATTERN.match(found):
            raise StripError(f"id {found!r} is not of the form {PREFIX}-001")
        if strip_id and found != strip_id:
            raise StripError(f"id {found!r} does not match its filename {strip_id!r}")

        title = str(meta.get("title") or "").strip()
        if not title:
            raise StripError(f"{found} has no title")

        raw_status = str(meta.get("status", Status.QUEUED))
        try:
            status = Status(raw_status)
        except ValueError as exc:
            allowed = ", ".join(s.value for s in Status)
            raise StripError(f"{found}: unknown status {raw_status!r} (want one of {allowed})") from exc

        return cls(
            id=found,
            title=title,
            status=status,
            created=_instant(meta.get("created"), found, "created"),
            due=_date(meta.get("due"), found, "due"),
            scheduled_start=_wallclock(meta.get("scheduled_start"), found, "scheduled_start"),
            scheduled_end=_wallclock(meta.get("scheduled_end"), found, "scheduled_end"),
            board=str(meta.get("board", "")),
            column=str(meta.get("column", "")),
            tags=tuple(str(t) for t in meta.get("tags", ())),
            priority=str(meta.get("priority", "")),
            started=_instant(meta.get("started"), found, "started"),
            completed=_instant(meta.get("completed"), found, "completed"),
            body=body,
        )


# ── field coercion ────────────────────────────────────────
#
# TOML hands back real `date` and `datetime` objects, so these check the *kind*
# of time rather than parsing strings. Getting the kind wrong is the failure
# these exist to catch: a `scheduled_start` that arrived with an offset is an
# instant pretending to be a wall clock, and it will drift by an hour twice a
# year without anything ever raising.


def _instant(value, strip_id: str, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise StripError(f"{strip_id}: {name} must be an offset date-time, e.g. 2026-08-14T09:12:03Z")
    return value


def _wallclock(value, strip_id: str, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is not None:
        raise StripError(f"{strip_id}: {name} must be a local date-time with no offset, e.g. 2026-08-14T14:00")
    return value


def _date(value, strip_id: str, name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise StripError(f"{strip_id}: {name} must be a plain date, e.g. 2026-08-14")
    return value


# ── the store ─────────────────────────────────────────────


class StripStore:
    """
    Every strip in the vault, one file each.

    `all()` is an O(n) directory walk. That is fine at the scale this runs at,
    and `index.py` later replaces this one method with an FTS query — which is
    the reason it is one method.
    """

    def __init__(self, vault: Vault | None = None) -> None:
        self.vault = vault or Vault()
        #: Files that failed to parse on the last `all()`, as `(path, message)`.
        #: Collected rather than raised so one hand-edited typo cannot blank the
        #: objectives screen — and surfaced rather than swallowed, because a
        #: strip that silently vanishes from your list is worse than an error.
        self.errors: list[tuple[Path, str]] = []

    @property
    def dir(self) -> Path:
        return self.vault.dirs["strips"]

    def path_for(self, strip_id: str) -> Path:
        return self.dir / f"{strip_id}.md"

    # ── identity ──────────────────────────────────────────

    def next_id(self) -> str:
        """
        The next unused callsign, derived from the directory itself.

        Files that are not strips are ignored rather than tripping this up — a
        stray `README.md` in the folder should not stop you making a task.
        """
        highest = 0
        if self.dir.is_dir():
            for path in self.dir.glob("*.md"):
                match = ID_PATTERN.match(path.stem)
                if match:
                    highest = max(highest, int(match.group(1)))
        return f"{PREFIX}-{highest + 1:0{ID_DIGITS}d}"

    # ── read ──────────────────────────────────────────────

    def read(self, strip_id: str) -> Strip | None:
        """One strip, or `None` if there is no such file. Raises on a bad one."""
        text = read_text(self.path_for(strip_id))
        return None if text is None else Strip.parse(text, strip_id)

    def all(self) -> list[Strip]:
        """
        Every readable strip, newest callsign last. Unreadable files land in
        `self.errors` instead of stopping the walk.
        """
        self.errors = []
        found: list[Strip] = []
        for path in sorted(self.dir.glob("*.md")) if self.dir.is_dir() else []:
            # A file that never claimed to be a strip is not a corrupt strip.
            # `next_id()` already ignores these; reporting them here would put a
            # permanent error on the SYSTEMS screen for a stray README.
            if not ID_PATTERN.match(path.stem):
                continue
            text = read_text(path)
            if text is None:
                self.errors.append((path, "unreadable"))
                continue
            try:
                found.append(Strip.parse(text, path.stem))
            except StripError as exc:
                self.errors.append((path, str(exc)))
        return found

    # ── write ─────────────────────────────────────────────

    def write(self, strip: Strip) -> Path:
        path = self.path_for(strip.id)
        atomic_write_text(path, strip.to_document())
        return path

    def create(self, title: str, body: str = "", **fields) -> Strip:
        """
        Mint a strip and write it.

        The id is re-checked against the filesystem in a loop rather than
        trusted from `next_id()` alone, so two creates in the same instant
        produce two strips instead of one overwriting the other.
        """
        number = int(ID_PATTERN.match(self.next_id()).group(1))
        while True:
            strip_id = f"{PREFIX}-{number:0{ID_DIGITS}d}"
            if not self.path_for(strip_id).exists():
                break
            number += 1

        strip = Strip(
            id=strip_id,
            title=title,
            created=fields.pop("created", None) or clock.now(),
            body=body,
            **fields,
        )
        self.write(strip)
        return strip

    def scrub(self, strip_id: str) -> Strip | None:
        """
        Cancel a strip. Sets the status; never unlinks the file.

        Deleting the record would make the vault disagree with its own history,
        and `archive/` already exists for anything that genuinely has to leave.
        """
        strip = self.read(strip_id)
        if strip is None:
            return None
        scrubbed = strip.with_status(Status.SCRUBBED)
        self.write(scrubbed)
        return scrubbed
