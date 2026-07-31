"""
The three legacy readers.

Fixtures here are written in the exact shapes v0.1's *writers* produce — not the
shapes its docstrings describe, which disagree with them in several places. The
inbox fixture in particular reproduces H1's concatenated line, because recovering
both halves of it is the one job `find_checkboxes` was given.

Nothing in this file mutates a vault; these readers only read.
"""

from datetime import date, datetime

from bloc.core.strips import Status
from bloc.jobs.legacy import (
    COLUMN_STATUS,
    read_agenda,
    read_all,
    read_board,
    read_inbox,
    sources_for,
)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestInbox:
    def test_a_plain_task(self, tmp_path):
        path = write(tmp_path / "inbox.md", "# Inbox\n\n- [ ] Call the dentist\n")
        found, faults = read_inbox(path)
        assert faults == []
        assert len(found) == 1
        assert found[0].title == "Call the dentist"
        assert found[0].status is Status.QUEUED
        assert found[0].kind == "inbox"

    def test_due_date_and_tags_leave_the_title(self, tmp_path):
        path = write(tmp_path / "inbox.md", "- [ ] Call the dentist 2026-08-14 #health #calls\n")
        found, _ = read_inbox(path)
        assert found[0].title == "Call the dentist"
        assert found[0].due == date(2026, 8, 14)
        assert found[0].tags == ("health", "calls")

    def test_a_completed_task_keeps_both_dates_apart(self, tmp_path):
        """
        v0.1 appends the completion stamp *after* the tags, so a done line can
        carry two bare dates. The first is the due date, the last is when it was
        finished — the disambiguation `parse_checkbox` was written for.
        """
        line = "- [x] Book the flights 2026-07-05 #travel  2026-07-11\n"
        found, _ = read_inbox(write(tmp_path / "inbox.md", line))
        assert found[0].status is Status.DONE
        assert found[0].due == date(2026, 7, 5)
        assert found[0].completed.date() == date(2026, 7, 11)

    def test_a_completion_date_becomes_an_aware_instant(self, tmp_path):
        """
        `Strip.completed` is an instant and the legacy format records a date, so
        the migration widens it — to local noon, which is the hour least likely
        to land on the wrong day under a timezone conversion.
        """
        path = write(tmp_path / "inbox.md", "- [x] Done thing  2026-07-11\n")
        found, _ = read_inbox(path)
        assert found[0].completed.tzinfo is not None
        assert found[0].completed.hour == 12

    def test_the_h1_concatenation_is_recovered_and_reported(self, tmp_path):
        """
        H1's bug dropped the trailing newline on rewrite, so the next append
        landed on the previous line and one task vanished from every reader.
        Both halves come back, and the split is reported so it can be checked
        before anything is written.
        """
        path = write(tmp_path / "inbox.md", "- [ ] Bravo - [ ] Charlie\n")
        found, faults = read_inbox(path)
        assert [item.title for item in found] == ["Bravo", "Charlie"]
        assert len(faults) == 1
        assert "split into 2" in faults[0].message

    def test_a_missing_inbox_is_not_an_error(self, tmp_path):
        assert read_inbox(tmp_path / "nope.md") == ([], [])

    def test_prose_and_headings_are_not_tasks(self, tmp_path):
        path = write(tmp_path / "inbox.md", "# Inbox\n\nsome notes about things\n")
        found, faults = read_inbox(path)
        assert found == [] and faults == []


class TestBoard:
    BOARD = """# Admin

## Inbox
- [ ] Look at the printer

## In Progress
- [ ] Rewrite the parser  📅 2026-09-01  #code  🔥

## Review
- [ ] Auth refactor

## Nonsense Column
- [ ] Buy an antenna

## Done
- [x] File the tax return
"""

    def read(self, tmp_path, text=None):
        return read_board(write(tmp_path / "admin.md", text or self.BOARD))

    def test_columns_map_onto_statuses(self, tmp_path):
        found, _ = self.read(tmp_path)
        by_title = {item.title: item for item in found}
        assert by_title["Look at the printer"].status is Status.QUEUED
        assert by_title["Rewrite the parser"].status is Status.ACTIVE
        assert by_title["File the tax return"].status is Status.DONE

    def test_review_is_active_because_status_is_not_column(self, tmp_path):
        """
        A card in review is still being worked on. `column` keeps the board's own
        word for it; `status` stays the closed five-value vocabulary the rest of
        the system understands.
        """
        found, _ = self.read(tmp_path)
        card = next(item for item in found if item.title == "Auth refactor")
        assert card.status is Status.ACTIVE
        assert card.column == "Review"

    def test_an_unrecognised_column_falls_to_queued_and_is_flagged(self, tmp_path):
        found, _ = self.read(tmp_path)
        card = next(item for item in found if item.title == "Buy an antenna")
        assert card.status is Status.QUEUED
        assert card.unmapped_column is True
        assert card.column == "Nonsense Column"

    def test_card_metadata_survives(self, tmp_path):
        found, _ = self.read(tmp_path)
        card = next(item for item in found if item.title == "Rewrite the parser")
        assert card.due == date(2026, 9, 1)
        assert card.tags == ("code",)
        assert card.priority == "high"

    def test_a_ticked_card_is_done_wherever_it_sits(self, tmp_path):
        found, _ = self.read(tmp_path, "## In Progress\n- [x] Already finished\n")
        assert found[0].status is Status.DONE
        assert found[0].unmapped_column is False

    def test_the_board_name_is_the_slugified_stem(self, tmp_path):
        found, _ = read_board(write(tmp_path / "Work Stuff.md", "## Inbox\n- [ ] A\n"))
        assert found[0].board == "work-stuff"

    def test_a_card_before_any_column_is_reported_not_dropped(self, tmp_path):
        """v0.1's loader discarded these silently, so a card could leave a board unnoticed."""
        text = "# Admin\n- [ ] Homeless card\n\n## Inbox\n- [ ] Fine\n"
        found, faults = self.read(tmp_path, text)
        assert [item.title for item in found] == ["Fine"]
        assert "before any column" in faults[0].message

    def test_every_mapped_column_names_a_real_status(self):
        assert all(isinstance(value, Status) for value in COLUMN_STATUS.values())


class TestAgenda:
    DAY = """# AGENDA · WEDNESDAY 29 JULY 2026

## 09:00 → 10:30 | DEEP WORK
> Build the RADAR module
- [ ] Draft README
- [ ] Push to git

## 14:00 → 15:00 | ADMIN ✓
"""

    def read(self, tmp_path, text=None, name="2026-07-29.md"):
        return read_agenda(write(tmp_path / name, text or self.DAY))

    def test_times_are_naive_and_dated_from_the_filename(self, tmp_path):
        """
        The wall-clock kind. A 14:00 block is 14:00 whatever the offset was that
        day — which is the entire reason S4 keeps the three kinds of time apart.
        """
        found, _ = self.read(tmp_path)
        block = found[0]
        assert block.scheduled_start == datetime(2026, 7, 29, 9, 0)
        assert block.scheduled_end == datetime(2026, 7, 29, 10, 30)
        assert block.scheduled_start.tzinfo is None

    def test_a_ticked_block_is_done(self, tmp_path):
        found, _ = self.read(tmp_path)
        assert found[1].title == "ADMIN"
        assert found[1].status is Status.DONE

    def test_an_unticked_block_stays_queued_however_old(self, tmp_path):
        """
        The migration never decides that an elapsed block happened. Inferring
        completion would fabricate history the vault is supposed to be the
        record of.
        """
        found, _ = self.read(tmp_path, "## 09:00 → 10:00 | ANCIENT\n", "1999-01-01.md")
        assert found[0].status is Status.QUEUED

    def test_the_description_becomes_the_body(self, tmp_path):
        found, _ = self.read(tmp_path)
        assert "Build the RADAR module" in found[0].body

    def test_nested_checkboxes_are_counted_not_extracted(self, tmp_path):
        """
        A block's own checkboxes stay in its body. `Strip` has no parent field,
        and inventing one inside a migration is scope nobody agreed to — so the
        count is reported instead, and the dry-run shows it.
        """
        found, _ = self.read(tmp_path)
        assert found[0].nested_tasks == 2
        assert "- [ ] Draft README" in found[0].body

    def test_a_block_crossing_midnight_ends_the_next_day(self, tmp_path):
        """
        `23:30 → 00:15` crosses midnight; it does not end before it starts.

        v0.1 held both times as strings, so this was invisible. In a typed field
        it would hand every view a negative duration. Found by running the
        verification checklist against an awkward vault, not by a test — this is
        the test written afterwards.
        """
        found, faults = self.read(tmp_path, "## 23:30 → 00:15 | LATE SHIFT\n")
        assert faults == []
        block = found[0]
        assert block.scheduled_start == datetime(2026, 7, 29, 23, 30)
        assert block.scheduled_end == datetime(2026, 7, 30, 0, 15)
        assert block.scheduled_end > block.scheduled_start

    def test_a_zero_length_block_still_ends_after_it_starts(self, tmp_path):
        found, _ = self.read(tmp_path, "## 09:00 → 09:00 | INSTANT\n")
        assert found[0].scheduled_end > found[0].scheduled_start

    def test_an_impossible_time_is_reported(self, tmp_path):
        found, faults = self.read(tmp_path, "## 25:00 → 26:00 | BAD\n")
        assert found == []
        assert "unreadable time" in faults[0].message

    def test_an_ascii_arrow_is_accepted(self, tmp_path):
        found, faults = self.read(tmp_path, "## 09:00 -> 10:00 | TYPED BY HAND\n")
        assert faults == []
        assert found[0].title == "TYPED BY HAND"

    def test_a_filename_that_is_not_a_date_is_reported(self, tmp_path):
        found, faults = self.read(tmp_path, name="notes.md")
        assert found == []
        assert "not a date" in faults[0].message

    def test_an_unreadable_header_is_reported_not_absorbed(self, tmp_path):
        """
        The bug this test exists for: a `## ` line that does not parse used to
        fall through to "append to the previous block's body", which swallowed
        both the broken header and everything under it without a word.
        """
        text = "## 09:00 → 10:00 | REAL\nsome notes\n## 9:00 - 10:00 writing\n"
        found, faults = self.read(tmp_path, text)
        assert len(found) == 1
        assert "9:00 - 10:00 writing" not in found[0].body
        assert "header not understood" in faults[0].message


class TestReadAll:
    def test_order_is_stable_so_callsigns_are_deterministic(self, tmp_path):
        from bloc.core.vault import Vault

        vault = Vault(tmp_path)
        write(vault.dirs["tasks"] / "inbox.md", "- [ ] From the inbox\n")
        write(vault.dirs["boards"] / "beta.md", "## Inbox\n- [ ] From beta\n")
        write(vault.dirs["boards"] / "alpha.md", "## Inbox\n- [ ] From alpha\n")
        write(vault.dirs["calendar"] / "2026-01-02.md", "## 09:00 → 10:00 | SECOND\n")
        write(vault.dirs["calendar"] / "2026-01-01.md", "## 09:00 → 10:00 | FIRST\n")

        titles = [item.title for item in read_all(vault)[0]]
        assert titles == ["From the inbox", "From alpha", "From beta", "FIRST", "SECOND"]
        # Two reads of an unchanged vault must agree, or a dry-run cannot be
        # trusted to predict the ids the real run will assign.
        assert titles == [item.title for item in read_all(vault)[0]]

    def test_sources_lists_every_file_including_unparseable_ones(self, tmp_path):
        from bloc.core.vault import Vault

        vault = Vault(tmp_path)
        write(vault.dirs["tasks"] / "inbox.md", "- [ ] A\n")
        write(vault.dirs["calendar"] / "notes.md", "not a date\n")
        names = [path.name for path in sources_for(vault)]
        assert names == ["inbox.md", "notes.md"]

    def test_an_empty_vault_yields_nothing(self, tmp_path):
        from bloc.core.vault import Vault

        assert read_all(Vault(tmp_path)) == ([], [])
