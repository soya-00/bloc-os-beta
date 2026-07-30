"""
The strip record.

Two clusters carry most of the weight. The round-trip tests assert that a value
written comes back **with its type intact** — a `due` that returns as a
`datetime` instead of a `date`, or a `scheduled_start` that returns with an
offset, is the bug that drifts an agenda block by an hour twice a year without
raising. And the store tests assert that a hand-edited typo costs you one strip
in an error list, never the whole screen.
"""

from datetime import UTC, date, datetime

import pytest

from bloc.core.strips import (
    BAY_ORDER,
    OPEN,
    PREFIX,
    Status,
    Strip,
    StripError,
    StripStore,
)
from bloc.core.vault import Vault


@pytest.fixture
def store(tmp_path):
    vault = Vault(tmp_path / "bloc")
    vault.ensure()
    return StripStore(vault)


def a_strip(**fields) -> Strip:
    base = {
        "id": "BLK-041",
        "title": "Call the dentist",
        "created": datetime(2026, 7, 21, 9, 12, 3, tzinfo=UTC),
    }
    return Strip(**{**base, **fields})


# ── the vocabulary ────────────────────────────────────────


class TestStatus:
    def test_five_states(self):
        assert len(Status) == 5

    def test_the_four_bays_exclude_scrubbed(self):
        """Cancelled work is hidden from the bays but never unlinked."""
        assert Status.SCRUBBED not in BAY_ORDER
        assert len(BAY_ORDER) == 4

    def test_holding_is_a_real_status(self):
        """
        Blocked on someone else is distinct from not started yet. Without it the
        HOLDING bay in the screens has nothing behind it.
        """
        assert Status.HOLDING in BAY_ORDER
        assert Status.HOLDING in OPEN

    def test_done_and_scrubbed_are_not_open(self):
        assert Status.DONE not in OPEN
        assert Status.SCRUBBED not in OPEN

    def test_serialises_as_a_plain_word(self):
        assert str(Status.HOLDING) == "holding"


# ── round trip ────────────────────────────────────────────


class TestRoundTrip:
    def test_minimal_strip(self):
        original = a_strip()
        assert Strip.parse(original.to_document()) == original

    def test_every_field(self):
        original = a_strip(
            status=Status.HOLDING,
            due=date(2026, 8, 14),
            scheduled_start=datetime(2026, 8, 14, 14, 0),
            scheduled_end=datetime(2026, 8, 14, 15, 30),
            board="admin",
            column="Review",
            tags=("health", "calls"),
            priority="high",
            started=datetime(2026, 7, 29, 10, 0, tzinfo=UTC),
            completed=datetime(2026, 7, 29, 11, 30, tzinfo=UTC),
            body="Ring the surgery before they close.",
        )
        assert Strip.parse(original.to_document()) == original

    def test_the_three_kinds_of_time_keep_their_kind(self):
        """The whole reason the strip stores dates as native TOML types."""
        parsed = Strip.parse(
            a_strip(
                due=date(2026, 8, 14),
                scheduled_start=datetime(2026, 8, 14, 14, 0),
            ).to_document()
        )
        assert isinstance(parsed.due, date) and not isinstance(parsed.due, datetime)
        assert parsed.scheduled_start.tzinfo is None
        assert parsed.created.tzinfo is not None

    def test_a_wallclock_time_does_not_acquire_an_offset(self):
        """A 14:00 block must still say 14:00 after a trip through disk."""
        parsed = Strip.parse(a_strip(scheduled_start=datetime(2026, 11, 14, 14, 0)).to_document())
        assert parsed.scheduled_start.hour == 14
        assert parsed.scheduled_start.tzinfo is None

    def test_empty_fields_are_left_out_of_the_document(self):
        """The file is meant to be read and hand-edited, not padded with blanks."""
        text = a_strip().to_document()
        for absent in ("board", "column", "priority", "tags", "due", "completed"):
            assert absent not in text

    def test_body_survives_a_frontmatter_fence(self):
        body = "first thought\n\n---\n\nsecond thought"
        assert Strip.parse(a_strip(body=body).to_document()).body == body

    def test_tags_round_trip_as_a_tuple(self):
        assert Strip.parse(a_strip(tags=("a", "b")).to_document()).tags == ("a", "b")


# ── strict parsing ────────────────────────────────────────


class TestParseRejects:
    def test_no_frontmatter(self):
        with pytest.raises(StripError, match="no frontmatter"):
            Strip.parse("# Just a note\n\nbody")

    def test_bad_id(self):
        with pytest.raises(StripError, match="not of the form"):
            Strip.parse("+++\nid = 'nope'\ntitle = 'x'\n+++\n")

    def test_id_disagreeing_with_its_filename(self):
        """The filename is the identity; a document that claims otherwise is corrupt."""
        with pytest.raises(StripError, match="does not match its filename"):
            Strip.parse(a_strip().to_document(), "BLK-999")

    def test_missing_title(self):
        with pytest.raises(StripError, match="no title"):
            Strip.parse("+++\nid = 'BLK-001'\ntitle = ''\n+++\n")

    def test_unknown_status_names_the_alternatives(self):
        with pytest.raises(StripError, match="unknown status"):
            Strip.parse("+++\nid = 'BLK-001'\ntitle = 'x'\nstatus = 'pending'\n+++\n")

    def test_created_must_carry_an_offset(self):
        with pytest.raises(StripError, match="offset date-time"):
            Strip.parse("+++\nid = 'BLK-001'\ntitle = 'x'\ncreated = 2026-08-14T09:12:03\n+++\n")

    def test_a_scheduled_time_must_not(self):
        """An instant pretending to be a wall clock drifts an hour twice a year."""
        with pytest.raises(StripError, match="no offset"):
            Strip.parse(
                "+++\nid = 'BLK-001'\ntitle = 'x'\nscheduled_start = 2026-08-14T14:00:00Z\n+++\n"
            )

    def test_due_must_be_a_plain_date(self):
        with pytest.raises(StripError, match="plain date"):
            Strip.parse("+++\nid = 'BLK-001'\ntitle = 'x'\ndue = 2026-08-14T00:00:00Z\n+++\n")


# ── behaviour ─────────────────────────────────────────────


class TestTransitions:
    def test_going_active_stamps_started(self):
        moved = a_strip().with_status(Status.ACTIVE)
        assert moved.status is Status.ACTIVE
        assert moved.started is not None

    def test_going_done_stamps_completed(self):
        moved = a_strip().with_status(Status.DONE)
        assert moved.completed is not None

    def test_an_existing_started_is_not_overwritten(self):
        first = datetime(2026, 7, 1, tzinfo=UTC)
        moved = a_strip(started=first).with_status(Status.ACTIVE)
        assert moved.started == first

    def test_holding_stamps_nothing(self):
        moved = a_strip().with_status(Status.HOLDING)
        assert moved.started is None and moved.completed is None

    def test_the_original_is_untouched(self):
        original = a_strip()
        original.with_status(Status.DONE)
        assert original.status is Status.QUEUED

    def test_strips_are_frozen(self):
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            a_strip().title = "changed"


class TestDerived:
    def test_overdue(self):
        assert a_strip(due=date(2026, 7, 1)).is_overdue(date(2026, 7, 29))

    def test_due_today_is_not_overdue(self):
        assert not a_strip(due=date(2026, 7, 29)).is_overdue(date(2026, 7, 29))

    def test_completed_work_is_never_overdue(self):
        """"What is pushing on me" has no useful answer that includes finished work."""
        late = a_strip(due=date(2026, 1, 1), status=Status.DONE)
        assert not late.is_overdue(date(2026, 7, 29))

    def test_no_due_date_is_never_overdue(self):
        assert not a_strip().is_overdue(date(2099, 1, 1))

    def test_a_scheduled_strip_is_an_agenda_block(self):
        assert a_strip(scheduled_start=datetime(2026, 8, 14, 14, 0)).is_scheduled
        assert not a_strip().is_scheduled


# ── the store ─────────────────────────────────────────────


class TestNextId:
    def test_empty_directory_starts_at_one(self, store):
        assert store.next_id() == f"{PREFIX}-001"

    def test_counts_from_the_highest_present(self, store):
        for name in ("BLK-001", "BLK-007", "BLK-003"):
            (store.dir / f"{name}.md").touch()
        assert store.next_id() == f"{PREFIX}-008"

    def test_gaps_are_not_reused(self, store):
        """A callsign is a permanent name; reusing one repoints every reference."""
        (store.dir / "BLK-005.md").touch()
        assert store.next_id() == f"{PREFIX}-006"

    def test_non_strip_files_are_ignored(self, store):
        """A stray README should not stop you making a task."""
        (store.dir / "README.md").touch()
        (store.dir / "notes-2026.md").touch()
        assert store.next_id() == f"{PREFIX}-001"

    def test_grows_past_three_digits(self, store):
        (store.dir / "BLK-999.md").touch()
        assert store.next_id() == f"{PREFIX}-1000"

    def test_missing_directory(self, tmp_path):
        assert StripStore(Vault(tmp_path / "nothing")).next_id() == f"{PREFIX}-001"


class TestCreate:
    def test_writes_a_readable_file(self, store):
        made = store.create("Call the dentist", tags=("health",))
        assert store.path_for(made.id).exists()
        assert store.read(made.id) == made

    def test_stamps_created(self, store):
        assert store.create("x").created is not None

    def test_ids_increment(self, store):
        assert [store.create(f"t{i}").id for i in range(3)] == ["BLK-001", "BLK-002", "BLK-003"]

    def test_two_creates_never_collide(self, store):
        """Even minted in the same instant, two strips are two files."""
        made = [store.create("Same title") for _ in range(5)]
        assert len({s.id for s in made}) == 5
        assert len(list(store.dir.glob("*.md"))) == 5

    def test_extra_fields_are_accepted(self, store):
        made = store.create("x", due=date(2026, 8, 14), status=Status.ACTIVE)
        assert store.read(made.id).due == date(2026, 8, 14)


class TestRead:
    def test_missing_strip_is_none(self, store):
        assert store.read("BLK-404") is None

    def test_a_corrupt_strip_raises(self, store):
        (store.dir / "BLK-001.md").write_text(
            "+++\nid = 'BLK-001'\ntitle = 'x'\nstatus = 'nonsense'\n+++\n"
        )
        with pytest.raises(StripError):
            store.read("BLK-001")


class TestAll:
    def test_empty_vault(self, store):
        assert store.all() == []

    def test_returns_every_strip_in_callsign_order(self, store):
        for title in ("a", "b", "c"):
            store.create(title)
        assert [s.id for s in store.all()] == ["BLK-001", "BLK-002", "BLK-003"]

    def test_one_corrupt_file_does_not_hide_the_others(self, store):
        """A hand-edited typo must cost one strip, never the whole screen."""
        store.create("good one")
        store.create("also good")
        (store.dir / "BLK-009.md").write_text(
            "+++\nid = 'BLK-009'\ntitle = 'typo'\nstatus = 'nope'\n+++\n"
        )

        found = store.all()
        assert [s.title for s in found] == ["good one", "also good"]
        assert len(store.errors) == 1
        assert "unknown status" in store.errors[0][1]

    def test_a_stray_non_strip_file_is_not_an_error(self, store):
        """
        `next_id()` already ignores these. Reporting them here would put a
        permanent error on the SYSTEMS screen for a README somebody dropped in.
        """
        store.create("real one")
        (store.dir / "README.md").write_text("just a note about this folder")
        (store.dir / "2026-notes.md").write_text("+++\nnope = 1\n+++\n")

        assert [s.title for s in store.all()] == ["real one"]
        assert store.errors == []

    def test_errors_reset_between_calls(self, store):
        (store.dir / "BLK-009.md").write_text("not a strip at all")
        store.all()
        (store.dir / "BLK-009.md").unlink()
        store.all()
        assert store.errors == []

    def test_an_unreadable_file_is_recorded_not_raised(self, store):
        (store.dir / "BLK-009.md").write_bytes(b"\xff\xfe\x00")
        store.all()
        assert len(store.errors) == 1


class TestScrub:
    def test_sets_the_status(self, store):
        made = store.create("Cancel me")
        assert store.scrub(made.id).status is Status.SCRUBBED

    def test_never_unlinks_the_file(self, store):
        """The vault is the record. A delete you cannot undo is data loss."""
        made = store.create("Cancel me")
        store.scrub(made.id)
        assert store.path_for(made.id).exists()
        assert store.read(made.id).title == "Cancel me"

    def test_missing_strip_is_none(self, store):
        assert store.scrub("BLK-404") is None
