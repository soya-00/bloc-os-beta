"""
What time it is, behind one seam.

Two reasons this is a module rather than `datetime.now()` at each call site.

**Tests must not sleep.** `PulseSession.remaining` derives entirely from
`started_at` and the current time — the background thread in `core/pulse.py`
computes nothing. That makes the timer trivially testable *provided* the current
time is controllable, and untestable otherwise.

**BLOC stores three kinds of time and they are not interchangeable.** An
instant, a calendar date and a local time-of-day answer different questions, and
v0.1 treats all three as `datetime.now()` with no timezone. `now()` and
`local_wallclock()` returning different types is the point, not an inconvenience
— see `formats.py` for the storage side.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC, date, datetime

_frozen: datetime | None = None


def now() -> datetime:
    """The current instant — timezone-aware, UTC. Use for anything that happened."""
    return _frozen if _frozen is not None else datetime.now(UTC)


def local_now() -> datetime:
    """The current instant as aware local time. Use for rendering."""
    return now().astimezone()


def today() -> date:
    """
    The local calendar date.

    Deliberately not `now().date()`, which is the *UTC* date and is therefore
    wrong for several hours a day in most of the world.
    """
    return local_now().date()


def local_wallclock() -> datetime:
    """
    The current local time with the offset dropped — a naive wall-clock reading.

    The conversion from an instant to a wall-clock time is lossy, so it lives in
    a named function rather than happening implicitly inside a formatter. If you
    are calling this, you are saying "the time on the wall matters, the instant
    does not", which is true of an agenda block and false of a completion stamp.
    """
    return local_now().replace(tzinfo=None)


@contextlib.contextmanager
def frozen(instant: datetime) -> Iterator[datetime]:
    """
    Pin `now()` for the duration of the block. Nests correctly.

    Requires an aware datetime: freezing to a naive one would leave `today()`
    and `local_wallclock()` guessing at an offset, which is the exact ambiguity
    this module exists to remove.
    """
    global _frozen
    if instant.tzinfo is None:
        raise ValueError(
            "freeze to an aware datetime — a naive one leaves today() ambiguous"
        )
    previous, _frozen = _frozen, instant
    try:
        yield instant
    finally:
        _frozen = previous
