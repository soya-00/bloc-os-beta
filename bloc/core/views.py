"""
Four views over one store.

This is the module that makes Part II-C's claim testable. A strip is a task, a
kanban card, an agenda block and a flight strip — but that is only true if all
four can be *derived*, rather than each being written separately. v0.1 had three
stores that could not talk; if these four views need four sources, the
unification was never real and `strips/` is just a fourth store with better
frontmatter.

    board()       group by column within a board
    agenda()      what is scheduled on a given day
    bays()        the four flight-strip bays
    objectives()  the flat list, filtered

**Pure functions over a list of strips.** They take `list[Strip]`, not a
`StripStore`, so every view is testable without a filesystem, and so a screen
that already holds strips does not re-read the vault to show them a second way.
Reading happens once, at the edge; `index.py` later replaces that read alone.

Sorting lives here rather than in the screens for the same reason the palette
lives in `theme.py`: two screens that sort differently are two screens that
disagree about which task is most urgent.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from bloc.core import clock
from bloc.core.strips import BAY_ORDER, OPEN, Status, Strip

#: Left-to-right display order for board columns.
#:
#: Board columns are free-form and one-file-per-strip records no ordering — in
#: `boards/*.md` the order *was* the file order, and the migration cannot carry
#: that across. This is the fallback, and it is correct for boards created from
#: v0.1's defaults. **S8 makes it configurable per board**, which is also what
#: gives an empty column somewhere to be declared: a column nothing is in cannot
#: be derived from strips at all, and on a kanban board that is exactly the
#: column you want to drop work into.
#:
#: Deliberately *not* shared with the migration's own column table. That one
#: infers a status from a column name and dies at S15b; this one orders columns
#: for display and lives on. Same words, different jobs, different lifetimes.
CANONICAL_COLUMNS: tuple[str, ...] = (
    "Inbox",
    "Backlog",
    "Todo",
    "In Progress",
    "Doing",
    "Review",
    "Blocked",
    "Waiting",
    "On Hold",
    "Done",
    "Complete",
)

#: Sorts after every known column, before the alphabetical tail.
_UNKNOWN = len(CANONICAL_COLUMNS)


# ── ordering ──────────────────────────────────────────────


def _column_rank(name: str) -> tuple[int, str]:
    lowered = name.strip().lower()
    for index, known in enumerate(CANONICAL_COLUMNS):
        if known.lower() == lowered:
            return index, ""
    return _UNKNOWN, lowered


def urgency(strip: Strip, today: date | None = None) -> tuple:
    """
    The one sort order for "what should I look at first".

    Overdue first, then by due date, then undated work, breaking ties on
    priority and finally on callsign so the order is total and stable. A total
    order matters more than the particular choice: a list that reorders itself
    between two identical renders is one you stop trusting.
    """
    today = today or clock.today()
    overdue = strip.is_overdue(today)
    return (
        0 if overdue else 1,
        strip.due or date.max,
        0 if strip.priority == "high" else 1,
        strip.id,
    )


def _by_urgency(strips: Iterable[Strip], today: date | None = None) -> list[Strip]:
    today = today or clock.today()
    return sorted(strips, key=lambda s: urgency(s, today))


# ── the views ─────────────────────────────────────────────


def objectives(
    strips: Sequence[Strip],
    *,
    status: Status | None = None,
    tag: str = "",
    board_name: str = "",
    include_closed: bool = False,
    today: date | None = None,
) -> list[Strip]:
    """
    The flat list, most urgent first.

    Closed work is excluded by default: `scrubbed` is cancelled and `done` is
    finished, and a list that shows both is a log rather than a list of things
    to do.
    """
    found = list(strips)
    if not include_closed:
        found = [s for s in found if s.status in OPEN]
    if status is not None:
        found = [s for s in found if s.status is status]
    if tag:
        found = [s for s in found if tag in s.tags]
    if board_name:
        found = [s for s in found if s.board == board_name]
    return _by_urgency(found, today)


def agenda(strips: Sequence[Strip], day: date | None = None) -> list[Strip]:
    """
    Everything scheduled on one day, in clock order.

    Sorted by start time rather than by urgency — an agenda that reordered
    itself by importance would not be an agenda. Scrubbed blocks are dropped;
    completed ones stay, because a day you have finished is still a day that
    happened.
    """
    day = day or clock.today()
    found = [
        strip
        for strip in strips
        if strip.scheduled_start is not None
        and strip.scheduled_start.date() == day
        and strip.status is not Status.SCRUBBED
    ]
    return sorted(found, key=lambda s: (s.scheduled_start, s.id))


def bays(strips: Sequence[Strip], day: date | None = None) -> dict[Status, list[Strip]]:
    """
    The four flight-strip bays: INCOMING · ACTIVE · HOLDING · LANDED.

    **What counts as "today's flying".** A strip is in play if it is due today
    or earlier and still open, or scheduled today, or currently `active` — and
    the LANDED bay holds what was completed today rather than everything ever
    finished.

    The overdue clause is the load-bearing one. A task vanishing from the board
    the day after it was due is how a task list quietly stops being trusted, and
    `pressure` exists as a colour role for precisely this case.

    Undated, unscheduled backlog deliberately does *not* appear. That is what
    `objectives()` is for; the bays are a day, not a workload.
    """
    day = day or clock.today()
    grouped: dict[Status, list[Strip]] = {status: [] for status in BAY_ORDER}

    for strip in strips:
        if strip.status is Status.DONE:
            if strip.completed is not None and _local_date(strip.completed) == day:
                grouped[Status.DONE].append(strip)
            continue
        if strip.status not in OPEN:
            continue
        if _in_play(strip, day):
            grouped[strip.status].append(strip)

    for status in BAY_ORDER:
        grouped[status] = _by_urgency(grouped[status], day)
    return grouped


def _in_play(strip: Strip, day: date) -> bool:
    if strip.status is Status.ACTIVE:
        return True
    if strip.due is not None and strip.due <= day:
        return True
    return strip.scheduled_start is not None and strip.scheduled_start.date() == day


def _local_date(value) -> date:
    """The calendar day an instant fell on, locally. Not its UTC date."""
    return value.astimezone().date()


def board(strips: Sequence[Strip], name: str) -> dict[str, list[Strip]]:
    """
    One board, grouped by column, columns in display order.

    Cards keep **callsign order within a column**, which is creation order —
    the closest thing to the manual arrangement `boards/*.md` recorded as file
    order. Sorting a board by urgency would silently rearrange a layout the user
    made by hand, which is the one thing a kanban board must not do.

    Scrubbed cards are dropped. Only columns that hold something appear; see
    `CANONICAL_COLUMNS` for why an empty column cannot be derived here.
    """
    grouped: dict[str, list[Strip]] = {}
    for strip in strips:
        if strip.board != name or strip.status is Status.SCRUBBED:
            continue
        grouped.setdefault(strip.column or "Inbox", []).append(strip)

    ordered = sorted(grouped, key=_column_rank)
    return {column: sorted(grouped[column], key=lambda s: s.id) for column in ordered}


def boards(strips: Sequence[Strip]) -> list[str]:
    """Every board that has at least one strip on it, alphabetically."""
    return sorted({strip.board for strip in strips if strip.board})


# ── derived readouts ──────────────────────────────────────


def overdue(strips: Sequence[Strip], today: date | None = None) -> list[Strip]:
    """Open work past its due date, most overdue first."""
    today = today or clock.today()
    return _by_urgency([s for s in strips if s.is_overdue(today)], today)


def counts(strips: Sequence[Strip], today: date | None = None) -> dict[str, int]:
    """The numbers the status bar and the home page show."""
    today = today or clock.today()
    return {
        "open": sum(1 for s in strips if s.status in OPEN),
        "overdue": sum(1 for s in strips if s.is_overdue(today)),
        "active": sum(1 for s in strips if s.status is Status.ACTIVE),
        "scheduled": len(agenda(strips, today)),
        "done_today": len(bays(strips, today)[Status.DONE]),
    }


# ── demonstration ─────────────────────────────────────────
#
# `python -m bloc.core.views --demo` renders all four views over the real vault.
# S7's verification is "create one strip, confirm it appears correctly in the
# board, agenda, flight-strip and list views without being written four times" —
# this makes that runnable rather than described. Plain text on purpose: `core`
# does not import `ui`, and a debug view that needed a theme would be a layering
# violation dressed up as a feature.


def _demo(root: str | None = None, today: date | None = None) -> int:
    from bloc.core.strips import StripStore
    from bloc.core.vault import Vault

    store = StripStore(Vault(root) if root else Vault())
    strips = store.all()
    today = today or clock.today()

    print(f"VAULT {store.vault.root}   {len(strips)} strips   {today}")
    if store.errors:
        print(f"  {len(store.errors)} unreadable: {[p.name for p, _ in store.errors]}")
    if not strips:
        print("\n  empty vault — nothing to show")
        return 0

    print(f"\nCOUNTS       {counts(strips, today)}")

    print("\nOBJECTIVES   (open, most urgent first)")
    for strip in objectives(strips, today=today):
        flag = "!" if strip.is_overdue(today) else " "
        due = strip.due or ""
        print(f"  {flag} {strip.id}  {strip.status.value:<8} {strip.title[:40]:<40} {due}")

    print(f"\nBAYS         ({today})")
    for status, held in bays(strips, today).items():
        names = ", ".join(s.id for s in held) or "—"
        print(f"  {status.value:<8} {len(held):>2}  {names}")

    print(f"\nAGENDA       ({today})")
    scheduled = agenda(strips, today)
    for strip in scheduled:
        print(f"  {strip.scheduled_start:%H:%M}  {strip.id}  {strip.title[:40]}")
    if not scheduled:
        print("  — nothing scheduled")

    for name in boards(strips):
        print(f"\nBOARD        {name}")
        for column, cards in board(strips, name).items():
            names = ", ".join(s.id for s in cards) or "—"
            print(f"  {column:<14} {len(cards):>2}  {names}")

    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m bloc.core.views")
    parser.add_argument("--demo", action="store_true", help="render all four views")
    parser.add_argument("--home", metavar="DIR", help="vault root, overriding BLOC_HOME")
    # Every view takes the day as an argument, so looking at another one costs a
    # flag. v0.1 could not do this at all: `AgendaFile` accepts a date and was
    # only ever constructed with the default, so there was no way to plan
    # tomorrow (Part XII). Here it falls out of the signatures for free.
    parser.add_argument("--day", metavar="YYYY-MM-DD", help="view another day (default today)")
    args = parser.parse_args(argv)

    if not args.demo:
        parser.print_help()
        return 1

    day = None
    if args.day:
        from bloc.core.formats import parse_date

        day = parse_date(args.day)
    return _demo(args.home, day)


if __name__ == "__main__":
    raise SystemExit(main())
