"""
The four views.

The load-bearing test is `TestOneStore`: a single strip, written once, appearing
correctly in the board, the agenda, the bays and the list. That is the whole
claim of Part II-C — if these four needed four sources, the unification was
never real and `strips/` is just a fourth store with nicer frontmatter.

Everything is built from `Strip` objects directly. Views take a list, not a
store, so none of this touches a filesystem.
"""

from datetime import UTC, date, datetime

from bloc.core.strips import Status, Strip
from bloc.core.views import (
    CANONICAL_COLUMNS,
    agenda,
    bays,
    board,
    boards,
    counts,
    objectives,
    overdue,
    urgency,
)

TODAY = date(2026, 8, 14)
YESTERDAY = date(2026, 8, 13)


def strip(id_, title="A thing", **fields) -> Strip:
    return Strip(id=id_, title=title, created=datetime(2026, 8, 1, tzinfo=UTC), **fields)


def at(day: date, hour: int = 9) -> datetime:
    """A naive wall-clock time — the kind a scheduled block carries."""
    return datetime(day.year, day.month, day.day, hour, 0)


def done_at(day: date, hour: int = 17) -> datetime:
    """An aware instant — the kind a completion carries."""
    return datetime(day.year, day.month, day.day, hour, 0).astimezone()


class TestObjectives:
    def test_closed_work_is_excluded_by_default(self):
        found = objectives(
            [
                strip("BLK-001", status=Status.QUEUED),
                strip("BLK-002", status=Status.DONE),
                strip("BLK-003", status=Status.SCRUBBED),
                strip("BLK-004", status=Status.HOLDING),
            ],
            today=TODAY,
        )
        assert [s.id for s in found] == ["BLK-001", "BLK-004"]

    def test_closed_work_can_be_asked_for(self):
        found = objectives(
            [strip("BLK-001"), strip("BLK-002", status=Status.DONE)],
            include_closed=True,
            today=TODAY,
        )
        assert len(found) == 2

    def test_overdue_sorts_before_everything(self):
        found = objectives(
            [
                strip("BLK-001", due=date(2026, 12, 1)),
                strip("BLK-002", due=YESTERDAY),
                strip("BLK-003"),
            ],
            today=TODAY,
        )
        assert [s.id for s in found] == ["BLK-002", "BLK-001", "BLK-003"]

    def test_undated_work_sorts_last(self):
        found = objectives(
            [strip("BLK-001"), strip("BLK-002", due=date(2026, 9, 1))], today=TODAY
        )
        assert [s.id for s in found] == ["BLK-002", "BLK-001"]

    def test_priority_breaks_a_tie_on_due_date(self):
        found = objectives(
            [
                strip("BLK-001", due=TODAY),
                strip("BLK-002", due=TODAY, priority="high"),
            ],
            today=TODAY,
        )
        assert [s.id for s in found] == ["BLK-002", "BLK-001"]

    def test_the_order_is_total_so_two_renders_agree(self):
        """
        A list that reorders itself between identical renders is one you stop
        trusting. Callsign is the final tiebreak, so the order is total.
        """
        same = [strip("BLK-003"), strip("BLK-001"), strip("BLK-002")]
        assert [s.id for s in objectives(same, today=TODAY)] == ["BLK-001", "BLK-002", "BLK-003"]

    def test_filters(self):
        pool = [
            strip("BLK-001", tags=("health",), board="admin"),
            strip("BLK-002", tags=("code",), board="admin"),
            strip("BLK-003", tags=("code",), board="home"),
            strip("BLK-004", status=Status.HOLDING),
        ]
        assert [s.id for s in objectives(pool, tag="code", today=TODAY)] == ["BLK-002", "BLK-003"]
        assert [s.id for s in objectives(pool, board_name="admin", today=TODAY)] == [
            "BLK-001",
            "BLK-002",
        ]
        assert [s.id for s in objectives(pool, status=Status.HOLDING, today=TODAY)] == ["BLK-004"]

    def test_urgency_is_exposed_so_screens_share_one_order(self):
        assert urgency(strip("BLK-001", due=YESTERDAY), TODAY) < urgency(
            strip("BLK-002", due=TODAY), TODAY
        )


class TestAgenda:
    POOL = [
        strip("BLK-001", scheduled_start=at(TODAY, 14)),
        strip("BLK-002", scheduled_start=at(TODAY, 9)),
        strip("BLK-003", scheduled_start=at(YESTERDAY, 9)),
        strip("BLK-004"),
    ]

    def test_only_that_day_in_clock_order(self):
        """
        Sorted by start time, not by urgency. An agenda that reordered itself by
        importance would not be an agenda.
        """
        assert [s.id for s in agenda(self.POOL, TODAY)] == ["BLK-002", "BLK-001"]

    def test_another_day_is_just_an_argument(self):
        """v0.1 could not do this at all — `AgendaFile` was only ever built with today."""
        assert [s.id for s in agenda(self.POOL, YESTERDAY)] == ["BLK-003"]

    def test_completed_blocks_stay_because_the_day_still_happened(self):
        pool = [strip("BLK-001", scheduled_start=at(TODAY), status=Status.DONE)]
        assert len(agenda(pool, TODAY)) == 1

    def test_scrubbed_blocks_are_dropped(self):
        pool = [strip("BLK-001", scheduled_start=at(TODAY), status=Status.SCRUBBED)]
        assert agenda(pool, TODAY) == []


class TestBays:
    def test_due_today_is_in_play(self):
        held = bays([strip("BLK-001", due=TODAY)], TODAY)
        assert [s.id for s in held[Status.QUEUED]] == ["BLK-001"]

    def test_overdue_work_stays_visible(self):
        """
        The load-bearing clause. A task vanishing from the board the day after it
        was due is how a task list quietly stops being trusted.
        """
        held = bays([strip("BLK-001", due=date(2026, 1, 1))], TODAY)
        assert [s.id for s in held[Status.QUEUED]] == ["BLK-001"]

    def test_active_work_shows_whatever_its_dates(self):
        held = bays([strip("BLK-001", status=Status.ACTIVE)], TODAY)
        assert [s.id for s in held[Status.ACTIVE]] == ["BLK-001"]

    def test_scheduled_today_is_in_play(self):
        held = bays([strip("BLK-001", scheduled_start=at(TODAY))], TODAY)
        assert [s.id for s in held[Status.QUEUED]] == ["BLK-001"]

    def test_undated_backlog_is_not_a_bay(self):
        """`objectives()` is the workload; the bays are a day."""
        held = bays([strip("BLK-001")], TODAY)
        assert all(held[status] == [] for status in held)

    def test_future_work_is_not_yet_in_play(self):
        held = bays([strip("BLK-001", due=date(2026, 12, 1))], TODAY)
        assert held[Status.QUEUED] == []

    def test_landed_holds_what_was_completed_that_day(self):
        pool = [
            strip("BLK-001", status=Status.DONE, completed=done_at(TODAY)),
            strip("BLK-002", status=Status.DONE, completed=done_at(YESTERDAY)),
        ]
        held = bays(pool, TODAY)
        assert [s.id for s in held[Status.DONE]] == ["BLK-001"]

    def test_a_done_strip_with_no_completion_time_lands_nowhere(self):
        """
        Migrated agenda blocks marked `✓` carry no completion timestamp, because
        the v0.1 format has nowhere to record one. They stay reachable through
        `agenda()` and through `objectives(include_closed=True)`, but the bays
        cannot claim they were finished on a day nothing says they were.
        """
        held = bays([strip("BLK-001", status=Status.DONE)], TODAY)
        assert held[Status.DONE] == []

    def test_scrubbed_work_is_never_in_a_bay(self):
        held = bays([strip("BLK-001", status=Status.SCRUBBED, due=TODAY)], TODAY)
        assert all(held[status] == [] for status in held)

    def test_all_four_bays_exist_even_when_empty(self):
        """The screen draws four columns whether or not there is anything in them."""
        held = bays([], TODAY)
        assert [status.value for status in held] == ["queued", "active", "holding", "done"]

    def test_bays_are_sorted_by_urgency(self):
        pool = [strip("BLK-001", due=TODAY), strip("BLK-002", due=YESTERDAY)]
        held = bays(pool, TODAY)
        assert [s.id for s in held[Status.QUEUED]] == ["BLK-002", "BLK-001"]


class TestBoard:
    POOL = [
        strip("BLK-003", board="admin", column="Done", status=Status.DONE),
        strip("BLK-001", board="admin", column="In Progress", status=Status.ACTIVE),
        strip("BLK-002", board="admin", column="Inbox"),
        strip("BLK-004", board="admin", column="Zebra Lane"),
        strip("BLK-005", board="admin", column="Aardvark Lane"),
        strip("BLK-006", board="home", column="Inbox"),
    ]

    def test_columns_come_back_in_workflow_order(self):
        assert list(board(self.POOL, "admin"))[:3] == ["Inbox", "In Progress", "Done"]

    def test_unknown_columns_follow_alphabetically(self):
        """
        A column order cannot be derived from strips — one file per strip records
        no ordering. Known names use the canonical workflow order; anything else
        sorts after it, predictably. S8 makes this configurable per board.
        """
        assert list(board(self.POOL, "admin"))[3:] == ["Aardvark Lane", "Zebra Lane"]

    def test_cards_keep_creation_order_within_a_column(self):
        """
        Sorting a board by urgency would silently rearrange a layout made by
        hand, which is the one thing a kanban board must not do.
        """
        pool = [
            strip("BLK-009", board="b", column="Inbox", due=date(2026, 1, 1)),
            strip("BLK-002", board="b", column="Inbox"),
        ]
        assert [s.id for s in board(pool, "b")["Inbox"]] == ["BLK-002", "BLK-009"]

    def test_a_card_with_no_column_lands_in_inbox(self):
        assert list(board([strip("BLK-001", board="b")], "b")) == ["Inbox"]

    def test_scrubbed_cards_are_dropped(self):
        pool = [strip("BLK-001", board="b", column="Inbox", status=Status.SCRUBBED)]
        assert board(pool, "b") == {}

    def test_boards_do_not_leak_into_each_other(self):
        assert [s.id for s in board(self.POOL, "home")["Inbox"]] == ["BLK-006"]

    def test_boards_lists_what_exists(self):
        assert boards(self.POOL) == ["admin", "home"]

    def test_strips_on_no_board_are_not_a_board(self):
        assert boards([strip("BLK-001")]) == []

    def test_the_canonical_order_has_no_duplicates(self):
        lowered = [name.lower() for name in CANONICAL_COLUMNS]
        assert len(set(lowered)) == len(lowered)


class TestReadouts:
    def test_overdue_lists_only_open_work(self):
        pool = [
            strip("BLK-001", due=YESTERDAY),
            strip("BLK-002", due=YESTERDAY, status=Status.DONE),
        ]
        assert [s.id for s in overdue(pool, TODAY)] == ["BLK-001"]

    def test_counts(self):
        pool = [
            strip("BLK-001", due=YESTERDAY),
            strip("BLK-002", status=Status.ACTIVE),
            strip("BLK-003", scheduled_start=at(TODAY)),
            strip("BLK-004", status=Status.DONE, completed=done_at(TODAY)),
            strip("BLK-005", status=Status.SCRUBBED),
        ]
        assert counts(pool, TODAY) == {
            "open": 3,
            "overdue": 1,
            "active": 1,
            "scheduled": 1,
            "done_today": 1,
        }


class TestOneStore:
    """
    Part II-C's actual claim, as a test.

    One strip, written once, seen from four angles. If this needed four records
    the object model would not be unified — it would be shared storage with a
    better filename.
    """

    ONE = strip(
        "BLK-041",
        "Rewrite the parser",
        status=Status.ACTIVE,
        due=TODAY,
        scheduled_start=at(TODAY, 9),
        board="admin",
        column="In Progress",
        tags=("code",),
    )

    def test_it_is_a_task(self):
        assert self.ONE in objectives([self.ONE], today=TODAY)

    def test_it_is_an_agenda_block(self):
        assert agenda([self.ONE], TODAY) == [self.ONE]

    def test_it_is_a_flight_strip(self):
        assert bays([self.ONE], TODAY)[Status.ACTIVE] == [self.ONE]

    def test_it_is_a_kanban_card(self):
        assert board([self.ONE], "admin") == {"In Progress": [self.ONE]}

    def test_all_four_views_return_the_same_object(self):
        """Not equal copies — the same instance, because there is one record."""
        from_list = objectives([self.ONE], today=TODAY)[0]
        from_agenda = agenda([self.ONE], TODAY)[0]
        from_bays = bays([self.ONE], TODAY)[Status.ACTIVE][0]
        from_board = board([self.ONE], "admin")["In Progress"][0]
        assert from_list is from_agenda is from_bays is from_board
