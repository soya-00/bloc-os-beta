"""
Filesystem primitives. Everything that touches disk goes through here.

Three v0.1 habits this module exists to end:

**Nothing was written atomically.** Fourteen write sites, all direct
`Path.write_text`, and six of them rewrite an entire file to change one record —
`AgendaFile.save()` rewrites the whole day to tick one block. On a device that
gets unplugged, an interrupted write costs the whole day's agenda, the whole
board, or the config. `atomic_write_text` makes a torn write impossible.

**Two slug functions, neither sanitising.** `core/vault.py:38` and
`tasks/kanban_manager.py:27` both lowercase and replace spaces, and stop there,
so `new_board("A/B")` resolves outside `boards/`.

**Collisions overwrote silently.** Two notes with the same title in the same
minute landed on one file; `new_board` on an existing name reopened it and then
overwrote it.
"""

from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from pathlib import Path

#: Longest slug BLOC will generate. Matches v0.1's note cap, and leaves room for
#: the date prefix inside the 255-byte limit every filesystem in play shares.
MAX_SLUG = 40

_UNSAFE = re.compile(r"[^a-z0-9]+")


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8") -> Path:
    """
    Write so a reader sees either the whole old file or the whole new one.

    The temp file is created in the *destination directory*, not the system temp
    directory: `os.replace` is only atomic within one filesystem, and `/tmp` is
    very often a different one. Content is fsynced before the rename so it is
    durable, and the directory is fsynced after so the rename itself survives
    power loss — the second is the step people skip, and it is the one that
    matters on a Pi with no UPS.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

    _fsync_dir(path.parent)
    return path


def _fsync_dir(directory: Path) -> None:
    """Durably record a rename. Silently skipped where it is not supported."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:  # pragma: no cover - Windows has no directory descriptor
        return
    try:
        os.fsync(fd)
    except OSError:  # pragma: no cover - some filesystems refuse
        pass
    finally:
        os.close(fd)


def read_text(path: Path | str, encoding: str = "utf-8") -> str | None:
    """
    Read a file, returning `None` for the cases a vault walk actually hits.

    A missing file, a directory, or something that is not text — all of which a
    `rglob("*.md")` can turn up — are answers rather than exceptions. v0.1's
    `Vault.search` calls `read_text` bare, so one non-UTF-8 file anywhere under
    `~/bloc` aborts the entire search with a traceback.
    """
    try:
        return Path(path).read_text(encoding=encoding)
    except (FileNotFoundError, IsADirectoryError, PermissionError, UnicodeDecodeError):
        return None


def slugify(text: str, max_len: int = MAX_SLUG) -> str:
    """
    A filesystem-safe stem: lowercase ASCII, hyphen separated, never empty.

    Deliberately aggressive — everything outside `[a-z0-9]` collapses to a
    hyphen, so path separators, `..`, colons, control characters, leading dots
    and Windows reserved punctuation cannot survive contact. The v0.1 versions
    replaced spaces and nothing else, which is why a board named `A/B` escaped
    its directory.

    ASCII rather than Unicode because the vault gets copied to a USB stick by
    the sync job, and that stick may well be FAT32.
    """
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = _UNSAFE.sub("-", folded.lower()).strip("-")
    return slug[:max_len].strip("-") or "untitled"


def unique_path(directory: Path | str, stem: str, suffix: str = ".md") -> Path:
    """
    A path that does not exist yet, suffixing `-2`, `-3` … on collision.

    Losing a note because it shares a title and a minute with another one is a
    silent failure with no recovery, and `unique_path` costs one `exists()` call.
    """
    directory = Path(directory)
    candidate = directory / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate
