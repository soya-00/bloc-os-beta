"""
One parser per format, and every parser symmetric with its writer.

v0.1 persists eight distinct date formats and **not one of them is used for both
writing and reading**. Every date written is re-read as an opaque string, by a
regex matching markup no writer produces, or not at all. That is how
`ui/autoflight.py:262` came to search for `**due:**` while `core/vault.py:76`
writes a bare positional date — so every flight strip renders `QUEUED` forever,
and has since the feature shipped.

The rule this module enforces, and the reason every function here has a
round-trip test: **a value that can be written must parse back equal.**

## Three kinds of time

BLOC stores three things that all look like "a time" and behave differently:

| Kind | On disk | Question it answers |
|---|---|---|
| instant | `2026-08-14T09:12:03Z` | *when did this happen* — created, completed |
| date | `2026-08-14` | *which day* — a due date |
| wall clock | `2026-08-14T14:00` | *what does the clock say* — an agenda block |

Storing all three as instants moves a 14:00 block to 13:00 after a clock change.
Storing all three naive makes a running timer wrong across the same boundary.
Splitting them costs one rule and gets both right.

**TOML already knows this.** Its offset-date-time, local-date and
local-date-time types are exactly these three, and `tomllib` parses them back to
aware `datetime`, `date` and naive `datetime` respectively. So a strip's
frontmatter stores dates natively rather than as strings, and the type survives
the round trip without this module being involved. The functions here are for
everywhere TOML is not: filenames, legacy files, and rendering.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import tomli_w

#: Frontmatter fence. `+++` rather than `---` because the v0.1 journal format
#: already uses `---` as its entry separator — a delimiter that collides with
#: existing content is a parser that works until it doesn't.
FENCE = "+++"

INSTANT_FMT = "%Y-%m-%dT%H:%M:%SZ"
DATE_FMT = "%Y-%m-%d"
WALLCLOCK_FMT = "%Y-%m-%dT%H:%M"

_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_TAG = re.compile(r"(?:^|\s)#([\w-]+)")
_DUE_MARKER = re.compile(r"📅\s*(\d{4}-\d{2}-\d{2})")
_PRIORITY_MARKER = "🔥"
#: A checkbox must start a line or follow whitespace, so a `-[x]` inside a word
#: is not a task.
_CHECKBOX = re.compile(r"(?:^|\s)-\s*\[([ xX])\]\s*")


# ── time ──────────────────────────────────────────────────


def format_instant(value: datetime) -> str:
    """Serialise an instant as UTC with a `Z` suffix. Requires an aware datetime."""
    if value.tzinfo is None:
        raise ValueError("an instant must be timezone-aware; use clock.now()")
    return value.astimezone(UTC).strftime(INSTANT_FMT)


def parse_instant(text: str) -> datetime:
    """Parse `2026-08-14T09:12:03Z` to an aware UTC datetime."""
    return datetime.strptime(text.strip(), INSTANT_FMT).replace(tzinfo=UTC)


def format_date(value: date) -> str:
    """Serialise a calendar date. Accepts a `datetime` and keeps only the date."""
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime(DATE_FMT)


def parse_date(text: str) -> date:
    """Parse `2026-08-14` to a `date`."""
    return datetime.strptime(text.strip(), DATE_FMT).date()


def format_wallclock(value: datetime) -> str:
    """
    Serialise a local time-of-day, with no offset.

    Rejects an aware datetime rather than quietly dropping its offset: the
    conversion is lossy and belongs at the call site, where
    `clock.local_wallclock()` makes it visible.
    """
    if value.tzinfo is not None:
        raise ValueError(
            "a wall-clock time must be naive; convert explicitly with "
            "clock.local_wallclock() so the loss of offset is visible"
        )
    return value.strftime(WALLCLOCK_FMT)


def parse_wallclock(text: str) -> datetime:
    """Parse `2026-08-14T14:00` to a naive datetime."""
    return datetime.strptime(text.strip(), WALLCLOCK_FMT)


# ── frontmatter ───────────────────────────────────────────


def split_frontmatter(text: str) -> tuple[dict, str]:
    """
    Split TOML frontmatter from the body. Returns `({}, text)` when there is none.

    Lenient by design — an unterminated fence yields the whole input as body
    rather than raising. A vault is hand-editable in any editor, so a half-typed
    document must stay readable rather than becoming an error dialog.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != FENCE:
        return {}, text

    for index in range(1, len(lines)):
        if lines[index].strip() == FENCE:
            meta = tomllib.loads("\n".join(lines[1:index]))
            return meta, "\n".join(lines[index + 1 :]).lstrip("\n")

    return {}, text


def join_frontmatter(data: dict, body: str = "") -> str:
    """Render TOML frontmatter above a body. Inverse of `split_frontmatter`."""
    meta = tomli_w.dumps(data).rstrip("\n")
    body = body.strip("\n")
    head = f"{FENCE}\n{meta}\n{FENCE}\n"
    return f"{head}\n{body}\n" if body else head


# ── markdown checkboxes ───────────────────────────────────


@dataclass(frozen=True)
class Checkbox:
    """One task parsed out of a markdown line, with its metadata separated."""

    title: str
    done: bool = False
    due: date | None = None
    completed: date | None = None
    priority: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


def find_checkboxes(line: str) -> list[Checkbox]:
    """
    Every task in a line — not the first.

    Finding all of them rather than assuming one is what lets the vault
    migration recover both halves of `- [ ] Bravo - [ ] Charlie`, a line shape
    v0.1 produced whenever a task was completed and another added: the rewrite
    paths dropped the trailing newline, so the next append concatenated onto the
    previous line and one task vanished from every reader.

    The cost is that a task whose title genuinely contains `- [ ]` splits in two.
    That is vanishingly rare, and the migration's dry-run prints every split
    before anything is written.
    """
    matches = list(_CHECKBOX.finditer(line))
    if not matches:
        return []

    found = []
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(line)
        found.append(parse_checkbox(line[match.end() : end], done=match.group(1) != " "))
    return found


def parse_checkbox(text: str, done: bool = False) -> Checkbox:
    """
    Split one task's trailing metadata out of its title.

    Handles both v0.1 encodings, which disagree with each other: `inbox.md`
    writes a bare positional date and `#tag` suffixes, while `boards/*.md` writes
    `📅 date`, `#tag` and `🔥`.

    Date disambiguation, which is the fiddly part. A `📅` date is unambiguously a
    due date. Bare dates are not: `complete_task` appends a completion stamp
    after the tags, while a kanban card's date is a due date, and both land on a
    `[x]` line. So on a completed line the last bare date is the completion stamp
    and anything before it is the due date — which is exactly what each writer
    produces.
    """
    tags = tuple(dict.fromkeys(_TAG.findall(text)))
    text = _TAG.sub(" ", text)

    priority = "high" if _PRIORITY_MARKER in text else ""
    text = text.replace(_PRIORITY_MARKER, " ")

    due: date | None = None
    marked = _DUE_MARKER.search(text)
    if marked:
        due = parse_date(marked.group(1))
        text = _DUE_MARKER.sub(" ", text)

    completed: date | None = None
    bare = _ISO_DATE.findall(text)
    if bare:
        if done:
            completed = parse_date(bare[-1])
            if due is None and len(bare) > 1:
                due = parse_date(bare[0])
        elif due is None:
            due = parse_date(bare[0])
        text = _ISO_DATE.sub(" ", text)

    return Checkbox(
        title=" ".join(text.split()),
        done=done,
        due=due,
        completed=completed,
        priority=priority,
        tags=tags,
    )


def render_checkbox(item: Checkbox) -> str:
    """
    Render a `Checkbox` back to a markdown line.

    Exists so the round trip is testable in both directions. Note that a title
    containing a `#word` or a bare ISO date cannot survive this format — which is
    precisely why strips store their metadata in frontmatter rather than inline,
    and why this renderer is used only where a legacy format is required.
    """
    parts = [f"- [{'x' if item.done else ' '}]", item.title]
    if item.due:
        parts.append(format_date(item.due))
    parts.extend(f"#{tag}" for tag in item.tags)
    if item.priority == "high":
        parts.append(_PRIORITY_MARKER)
    if item.completed:
        parts.append(format_date(item.completed))
    return " ".join(parts)
