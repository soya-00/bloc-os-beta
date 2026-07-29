"""
The filesystem — the single source of truth.

Markdown on disk stays canonical. Nothing here caches, and `index.py` will later
be a rebuildable SQLite mirror that can be deleted without losing anything.

Two shifts from v0.1's `core/vault.py`:

**Notes become readable.** v0.1 wrote `# title`, a bare tag line and a body, and
then never parsed any of it — `list_notes` stats files, `search` does substring
matching, and the title, tags and creation time are write-only. New notes carry
TOML frontmatter; old ones are read by falling back to the H1 and the tag line,
so **no note migration is needed** and existing files keep working untouched.

**Tasks are gone from here.** They become strips in S5, so porting
`list_tasks`/`new_task`/`complete_task` would mean writing code deleted a week
later. The legacy shell keeps its own copy until the surface that replaces it
lands.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from bloc.core import clock
from bloc.core.files import atomic_write_text, read_text, slugify, unique_path
from bloc.core.formats import join_frontmatter, split_frontmatter

#: Vault format version, stamped in `.bloc-version`. Bumped by the strip
#: migration; formats *will* change again, and changing them without a recorded
#: version is how a migration silently runs twice or not at all.
VAULT_VERSION = 1

#: Environment override for the vault root. Lets the migration dry-run against a
#: copy, and lets tests use `tmp_path` without monkeypatching `Path.home`.
ROOT_ENV = "BLOC_HOME"

_NOTE_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d{2})-(\d{2})-")
_HEADING = re.compile(r"^#\s+(.+)$")
_TAG = re.compile(r"(?:^|\s)#([\w-]+)")

#: How far into a legacy note to look for its tag line. v0.1 wrote it as the
#: third line; scanning the whole document would collect every `#word` in the
#: prose, including comments inside fenced code.
_LEGACY_HEADER_LINES = 4


@dataclass(frozen=True)
class Note:
    path: Path
    title: str
    body: str = ""
    created: datetime | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Hit:
    """One search result."""

    path: Path
    line: int
    text: str


class Vault:
    """Directory layout and document CRUD. Knows nothing about the terminal."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or os.environ.get(ROOT_ENV) or Path.home() / "bloc")
        self.dirs: dict[str, Path] = {
            "notes": self.root / "notes",
            "journal": self.root / "journal",
            "strips": self.root / "strips",
            "debriefs": self.root / "debriefs",
            "archive": self.root / "archive",
            "config": self.root / "config",
            "sessions": self.root / "sessions",
            # Legacy locations. Addressable so the migration can find them,
            # never created — a fresh vault should not sprout directories for
            # formats it will never write.
            "tasks": self.root / "tasks",
            "boards": self.root / "tasks" / "boards",
            "calendar": self.root / "calendar",
        }
        self._legacy = {"tasks", "boards", "calendar"}

    def ensure(self) -> None:
        """
        Create the directories BLOC writes to.

        Not called from `__init__`: constructing a `Vault` to read a path should
        not have the side effect of creating nine directories, which is how v0.1
        scattered empty `exports/` folders into every test run.
        """
        for name, path in self.dirs.items():
            if name not in self._legacy:
                path.mkdir(parents=True, exist_ok=True)

    # ── version ───────────────────────────────────────────

    @property
    def version_file(self) -> Path:
        return self.root / ".bloc-version"

    def version(self) -> int | None:
        """The vault's format version, or `None` if it predates versioning."""
        raw = read_text(self.version_file)
        try:
            return int(raw.strip()) if raw else None
        except ValueError:
            return None

    def set_version(self, version: int = VAULT_VERSION) -> None:
        atomic_write_text(self.version_file, f"{version}\n")

    # ── notes ─────────────────────────────────────────────

    def write_note(self, title: str, body: str = "", tags: tuple[str, ...] = ()) -> Path:
        """
        Write a new note and return its path.

        The date-time filename prefix is kept from v0.1 because it makes a plain
        directory listing chronological, which is worth more than a tidy name.
        What changes is that the slug is sanitised and the path is unique, so a
        title of `../../etc/passwd` stays inside `notes/` and two notes sharing a
        title and a minute are two files.
        """
        created = clock.local_now()
        stem = f"{created:%Y-%m-%d-%H-%M}-{slugify(title)}"
        path = unique_path(self.dirs["notes"], stem)

        meta: dict = {"title": title, "created": clock.now()}
        if tags:
            meta["tags"] = list(tags)

        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, join_frontmatter(meta, body))
        return path

    def read_note(self, path: Path | str) -> Note | None:
        """
        Read a note, whichever format it is in.

        Frontmatter wins when present. Otherwise the title comes from the first
        H1, tags from the header region, and the creation time from the filename
        stamp — the three things v0.1 wrote and never read back.
        """
        path = Path(path)
        raw = read_text(path)
        if raw is None:
            return None

        meta, body = split_frontmatter(raw)
        if meta:
            created = meta.get("created")
            return Note(
                path=path,
                title=str(meta.get("title", path.stem)),
                body=body,
                created=created if isinstance(created, datetime) else None,
                tags=tuple(meta.get("tags", ())),
            )

        lines = body.splitlines()
        heading = next((_HEADING.match(line) for line in lines if _HEADING.match(line)), None)
        header = "\n".join(lines[:_LEGACY_HEADER_LINES])
        return Note(
            path=path,
            title=heading.group(1).strip() if heading else path.stem,
            body=body,
            created=self._stamp_from_name(path),
            tags=tuple(dict.fromkeys(_TAG.findall(header))),
        )

    @staticmethod
    def _stamp_from_name(path: Path) -> datetime | None:
        """Recover a creation time from v0.1's `YYYY-MM-DD-HH-MM-slug` filename."""
        match = _NOTE_STAMP.match(path.name)
        if not match:
            return None
        day, hour, minute = match.groups()
        try:
            return datetime.fromisoformat(f"{day}T{hour}:{minute}")
        except ValueError:  # pragma: no cover - regex already constrains this
            return None

    def list_notes(self) -> list[Path]:
        """Every note, newest first."""
        notes = list(self.dirs["notes"].glob("*.md"))
        notes.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return notes

    # ── journal ───────────────────────────────────────────

    def append_journal(self, text: str, day: date | None = None) -> Path:
        """
        Append an entry to a day's journal.

        A real append rather than v0.1's read-whole-then-write-whole. Both are
        non-atomic, but the failure modes are not comparable: a torn append loses
        the tail of the entry being written, while a torn rewrite can lose the
        entire day.
        """
        day = day or clock.today()
        path = self.dirs["journal"] / f"{day.isoformat()}.md"
        stamp = f"{clock.local_now():%H:%M}"

        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            entry = f"\n\n---\n*{stamp}*\n\n{text}\n"
        else:
            entry = f"# Journal — {day.isoformat()}\n\n*{stamp}*\n\n{text}\n"

        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(entry)
            handle.flush()
            os.fsync(handle.fileno())
        return path

    # ── search ────────────────────────────────────────────

    def search(self, query: str, limit: int = 200) -> list[Hit]:
        """
        Substring search across the vault. One O(n) walk, deliberately.

        `index.py` replaces this single function with an FTS query later, which
        is the whole reason it is one function. Two v0.1 bugs fixed on the way:
        the archive exclusion was `if "archive" in str(path)`, a substring test
        against the whole path that also hid any note whose own name contained
        the word; and an unguarded `read_text` meant one non-UTF-8 file anywhere
        under the root aborted the entire search.
        """
        if not query:
            return []

        needle = query.lower()
        hits: list[Hit] = []
        for path in sorted(self.root.rglob("*.md")):
            if "archive" in path.relative_to(self.root).parts:
                continue
            content = read_text(path)
            if content is None:
                continue
            for number, line in enumerate(content.splitlines(), start=1):
                if needle in line.lower():
                    hits.append(Hit(path, number, line.strip()))
                    if len(hits) >= limit:
                        return hits
        return hits
