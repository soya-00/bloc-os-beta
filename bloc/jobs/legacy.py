"""
The three v0.1 vault formats, read one last time.

This module exists to be deleted. It is the only place that understands
`inbox.md`, `boards/*.md` and `calendar/YYYY-MM-DD.md`, and it dies with
`migrate.py` at S15b once nothing reads those formats any more. Keeping the
doomed parsers in their own file is what makes that a single deletion rather
than an archaeology exercise.

**Pure by construction.** Every function here takes a path and returns records
and faults. Nothing writes, nothing mints an id, nothing decides what to keep.
That lives in `migrate.py`, so the half that can destroy data is small, and
these readers can be exercised against fixture files without a vault, a store or
a single mutation.

## Most of the parsing already exists

`formats.parse_checkbox()` was written in S4 against *both* v0.1 checkbox
encodings — `inbox.md`'s bare positional date and `boards/*.md`'s
`📅`/`#tag`/`🔥` — including the rule that decides whether a bare date on a
completed line is a due date or a completion stamp. `formats.find_checkboxes()`
returns every task in a line rather than the first, specifically so this
migration recovers both halves of `- [ ] Bravo - [ ] Charlie`, the line shape
H1's bug produced. Neither needed rewriting; this module calls them.

Only the agenda header wanted a parser of its own, and it is one regex.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

from bloc.core.files import read_text, slugify
from bloc.core.formats import find_checkboxes, parse_date
from bloc.core.strips import Status

#: `## 09:00 → 10:30 | DEEP WORK`. `->` is accepted alongside `→` because the
#: file is hand-editable and an ASCII arrow is what anyone types; salvaging it
#: costs one alternation and saves a block from being reported as unreadable.
AGENDA_HEADER = re.compile(r"^##\s+(\d{1,2}:\d{2})\s*(?:→|->)\s*(\d{1,2}:\d{2})\s*\|\s*(.+?)\s*$")

#: A line that meant to be an agenda header. Used only to tell "this is prose"
#: apart from "this is a header I could not read" — the second deserves a
#: warning, the first does not.
AGENDA_HEADER_ISH = re.compile(r"^##\s")

#: `- [ ] Draft README` inside a block description. Counted, never extracted.
NESTED_TASK = re.compile(r"^\s*-\s*\[[ xX]\]")

#: v0.1's completion mark on an agenda block.
DONE_MARK = "✓"

#: Board column → status. Deliberately small: `KanbanBoard.DEFAULT_COLUMNS` is
#: `Inbox · In Progress · Review · Done`, so most real boards carry exactly
#: these. Anything unrecognised falls through to `queued` and is flagged as
#: unmapped in the dry-run rather than guessed at.
#:
#: **`Review` maps to `active`, not to a status of its own.** Status is a closed
#: five-value vocabulary; `column` is free-form board position. A card in review
#: is still being worked on. Conflating the two is what would make boards and
#: objectives disagree about the same strip.
COLUMN_STATUS: dict[str, Status] = {
    "inbox": Status.QUEUED,
    "backlog": Status.QUEUED,
    "todo": Status.QUEUED,
    "in progress": Status.ACTIVE,
    "doing": Status.ACTIVE,
    "review": Status.ACTIVE,
    "blocked": Status.HOLDING,
    "waiting": Status.HOLDING,
    "on hold": Status.HOLDING,
    "done": Status.DONE,
    "complete": Status.DONE,
}

#: Hour a legacy completion *date* is widened to when it becomes an instant.
#: Noon rather than midnight because midnight is the value most likely to cross
#: a day boundary under a timezone conversion, and a completion stamp on the
#: wrong day is worse than one that is vague about the hour.
COMPLETION_HOUR = 12


@dataclass(frozen=True)
class Proposal:
    """
    One strip the migration would create, and the line it came from.

    Carries no id: minting callsigns is the migration's job, and a reader that
    allocated them could not be run twice without side effects.
    """

    source: Path
    line: int
    kind: str  # "inbox" | "board" | "agenda"
    title: str
    status: Status

    due: date | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    board: str = ""
    column: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    priority: str = ""
    completed: datetime | None = None
    body: str = ""

    #: Set when a board column was not in `COLUMN_STATUS`, so the dry-run can
    #: show which statuses were inferred and which fell through.
    unmapped_column: bool = False
    #: Checkbox lines left inside an agenda block's body. Reported, not extracted.
    nested_tasks: int = 0

    def to_fields(self) -> dict:
        """The keyword arguments `StripStore.create` wants. Drops the provenance."""
        return {
            "status": self.status,
            "due": self.due,
            "scheduled_start": self.scheduled_start,
            "scheduled_end": self.scheduled_end,
            "board": self.board,
            "column": self.column,
            "tags": self.tags,
            "priority": self.priority,
            "completed": self.completed,
        }


@dataclass(frozen=True)
class Fault:
    """Something a reader could not understand. Never silently dropped."""

    source: Path
    line: int
    message: str


Reading = tuple[list[Proposal], list[Fault]]


def _completion_instant(day: date) -> datetime:
    """Widen a legacy completion date to an aware instant at local noon."""
    return datetime.combine(day, time(COMPLETION_HOUR)).astimezone()


# ── inbox ─────────────────────────────────────────────────


def read_inbox(path: Path) -> Reading:
    """
    `~/bloc/tasks/inbox.md` — `- [ ] title <date> #tag`, completed lines
    carrying a trailing completion stamp.

    Every checkbox on a line is taken, not just the first. A line yielding more
    than one is reported: it is almost certainly H1's concatenation bug, and on
    the vanishingly rare occasion it is a title genuinely containing `- [ ]`,
    the warning is what lets you notice before anything is written.
    """
    proposals: list[Proposal] = []
    faults: list[Fault] = []

    text = read_text(path)
    if text is None:
        return proposals, faults

    for number, line in enumerate(text.splitlines(), start=1):
        found = find_checkboxes(line)
        if not found:
            continue
        if len(found) > 1:
            faults.append(
                Fault(path, number, f"line split into {len(found)} tasks (H1 concatenation)")
            )
        for item in found:
            if not item.title:
                faults.append(Fault(path, number, "checkbox with no title, skipped"))
                continue
            proposals.append(
                Proposal(
                    source=path,
                    line=number,
                    kind="inbox",
                    title=item.title,
                    status=Status.DONE if item.done else Status.QUEUED,
                    due=item.due,
                    tags=item.tags,
                    priority=item.priority,
                    completed=_completion_instant(item.completed) if item.completed else None,
                )
            )
    return proposals, faults


# ── boards ────────────────────────────────────────────────


def read_board(path: Path) -> Reading:
    """
    `~/bloc/tasks/boards/<name>.md` — `## Column` headings over card lines.

    The board identifier is the filename stem, slugified. A card outside any
    column heading is a fault rather than a guess: v0.1's own loader silently
    discarded those, which is how a card could vanish from a board without
    anyone noticing.
    """
    proposals: list[Proposal] = []
    faults: list[Fault] = []

    text = read_text(path)
    if text is None:
        return proposals, faults

    board = slugify(path.stem)
    column = ""

    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            column = line[3:].strip()
            continue

        found = find_checkboxes(line)
        if not found:
            continue
        if not column:
            faults.append(Fault(path, number, "card before any column heading, skipped"))
            continue
        if len(found) > 1:
            faults.append(Fault(path, number, f"line split into {len(found)} cards"))

        mapped = COLUMN_STATUS.get(column.lower())
        for item in found:
            if not item.title:
                faults.append(Fault(path, number, "card with no title, skipped"))
                continue
            # A ticked card is done wherever it sits. The column only decides
            # the status of cards that are still open.
            status = Status.DONE if item.done else (mapped or Status.QUEUED)
            proposals.append(
                Proposal(
                    source=path,
                    line=number,
                    kind="board",
                    title=item.title,
                    status=status,
                    due=item.due,
                    tags=item.tags,
                    priority=item.priority,
                    completed=_completion_instant(item.completed) if item.completed else None,
                    board=board,
                    column=column,
                    unmapped_column=mapped is None and not item.done,
                )
            )
    return proposals, faults


# ── agenda ────────────────────────────────────────────────


def read_agenda(path: Path) -> Reading:
    """
    `~/bloc/calendar/YYYY-MM-DD.md` — `## HH:MM → HH:MM | LABEL` with free-text
    description lines beneath.

    **The day comes from the filename**, which is the only place v0.1 records
    it; the file's own `# AGENDA · …` heading is prose. A filename that is not a
    date is a fault, because a block with no day cannot become a scheduled strip.

    Times become **naive** datetimes — the wall-clock kind. A 14:00 block is
    14:00 whatever the offset was that day, which is the whole reason S4 splits
    the three kinds of time apart.

    **An unticked block stays `queued` however old it is.** Marking elapsed
    blocks done would fabricate completion history, and the vault is the record.
    """
    proposals: list[Proposal] = []
    faults: list[Fault] = []

    text = read_text(path)
    if text is None:
        return proposals, faults

    try:
        day = parse_date(path.stem)
    except ValueError:
        faults.append(Fault(path, 0, f"filename {path.name!r} is not a date, file skipped"))
        return proposals, faults

    def flush(pending: Proposal | None, body: list[str]) -> None:
        if pending is None:
            return
        proposals.append(
            replace(
                pending,
                body="\n".join(body).strip(),
                nested_tasks=sum(1 for entry in body if NESTED_TASK.match(entry)),
            )
        )

    pending: Proposal | None = None
    body: list[str] = []

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        match = AGENDA_HEADER.match(line)
        if match:
            flush(pending, body)
            body = []
            start_text, end_text, label = match.groups()
            done = label.endswith(DONE_MARK)
            label = label.removesuffix(DONE_MARK).strip()
            if not label:
                faults.append(Fault(path, number, "block with no label, skipped"))
                pending = None
                continue
            try:
                start = _wallclock(day, start_text)
                end = _wallclock(day, end_text)
            except ValueError as exc:
                faults.append(Fault(path, number, f"unreadable time: {exc}"))
                pending = None
                continue
            if end <= start:
                # `23:30 → 00:15` is a block that crosses midnight, not a block
                # that ends before it starts. v0.1 stored both times as strings
                # so this was invisible; in a typed field it would give every
                # view a negative duration.
                end += timedelta(days=1)
            pending = Proposal(
                source=path,
                line=number,
                kind="agenda",
                title=label,
                status=Status.DONE if done else Status.QUEUED,
                scheduled_start=start,
                scheduled_end=end,
            )
        elif AGENDA_HEADER_ISH.match(line):
            # A `## ` line is a heading, never body text. Checked *before* the
            # body branch: an unreadable header falling through to "append to
            # the previous block" is exactly the silent absorption this tool
            # exists to prevent, and it would take the block's description with
            # it without a word.
            flush(pending, body)
            pending, body = None, []
            faults.append(
                Fault(path, number, f"header not understood, block skipped: {line.strip()!r}")
            )
        elif pending is not None:
            body.append(line)

    flush(pending, body)
    return proposals, faults


def _wallclock(day: date, text: str) -> datetime:
    """`HH:MM` on a given day, as a naive local datetime."""
    hour, minute = (int(part) for part in text.split(":"))
    return datetime.combine(day, time(hour, minute))


# ── the whole vault ───────────────────────────────────────


def read_all(vault) -> Reading:
    """
    Every legacy record in a vault, in a stable order: inbox, then boards by
    name, then calendar days by date.

    Ordering is deliberate rather than incidental — callsigns are allocated in
    this order, so a dry-run and the real run assign the same id to the same
    task, and two dry-runs are identical.
    """
    proposals: list[Proposal] = []
    faults: list[Fault] = []

    for path in sources_for(vault):
        if path.parent == vault.dirs["boards"]:
            reader = read_board
        elif path.parent == vault.dirs["calendar"]:
            reader = read_agenda
        else:
            reader = read_inbox
        found, problems = reader(path)
        proposals.extend(found)
        faults.extend(problems)

    return proposals, faults


def sources_for(vault) -> list[Path]:
    """Every legacy file the migration would move, whether or not it parsed."""
    found = [vault.dirs["tasks"] / "inbox.md"]
    for key in ("boards", "calendar"):
        directory = vault.dirs[key]
        if directory.is_dir():
            found.extend(sorted(directory.glob("*.md")))
    return [path for path in found if path.is_file()]
