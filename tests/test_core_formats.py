"""
Round-trip tests. This file is the point of `formats.py`.

v0.1 persists eight date formats and uses none of them symmetrically, which is
how `ui/autoflight.py` came to parse `**due:**` markup that no writer produces.
Every assertion here says the same thing in a different place: what was written
parses back equal.
"""

import time
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from bloc.core.formats import (
    Checkbox,
    find_checkboxes,
    format_date,
    format_instant,
    format_wallclock,
    join_frontmatter,
    parse_checkbox,
    parse_date,
    parse_instant,
    parse_wallclock,
    render_checkbox,
    split_frontmatter,
)


class TestInstant:
    def test_round_trip(self):
        instant = datetime(2026, 8, 14, 9, 12, 3, tzinfo=UTC)
        assert parse_instant(format_instant(instant)) == instant

    def test_shape(self):
        assert format_instant(datetime(2026, 8, 14, 9, 12, 3, tzinfo=UTC)) == (
            "2026-08-14T09:12:03Z"
        )

    def test_non_utc_input_is_normalised(self):
        """Same moment, one representation."""
        sydney = timezone(timedelta(hours=10))
        instant = datetime(2026, 8, 14, 19, 12, 3, tzinfo=sydney)
        assert format_instant(instant) == "2026-08-14T09:12:03Z"

    def test_naive_is_rejected(self):
        with pytest.raises(ValueError, match="aware"):
            format_instant(datetime(2026, 8, 14, 9, 12, 3))


class TestDate:
    def test_round_trip(self):
        assert parse_date(format_date(date(2026, 8, 14))) == date(2026, 8, 14)

    def test_accepts_a_datetime_and_keeps_only_the_day(self):
        assert format_date(datetime(2026, 8, 14, 23, 59)) == "2026-08-14"


class TestWallclock:
    def test_round_trip(self):
        block = datetime(2026, 8, 14, 14, 0)
        assert parse_wallclock(format_wallclock(block)) == block

    def test_carries_no_offset(self):
        assert format_wallclock(datetime(2026, 8, 14, 14, 0)) == "2026-08-14T14:00"

    def test_aware_is_rejected(self):
        """Dropping an offset silently is how a 14:00 block becomes 13:00."""
        with pytest.raises(ValueError, match="naive"):
            format_wallclock(datetime(2026, 8, 14, 14, 0, tzinfo=UTC))

    @pytest.mark.skipif(not hasattr(time, "tzset"), reason="POSIX only")
    def test_a_block_survives_a_dst_change(self, monkeypatch):
        """
        The decision this format exists for: 14:00 in August is still 14:00 in
        November, in a zone that changes offset between them.
        """
        monkeypatch.setenv("TZ", "Europe/London")
        time.tzset()

        summer = datetime(2026, 8, 14, 14, 0)
        winter = datetime(2026, 11, 14, 14, 0)
        assert format_wallclock(summer).endswith("T14:00")
        assert format_wallclock(winter).endswith("T14:00")
        assert parse_wallclock(format_wallclock(winter)).hour == 14

        monkeypatch.delenv("TZ")
        time.tzset()


class TestFrontmatter:
    def test_round_trip(self):
        meta = {"title": "Call the dentist", "tags": ["health"]}
        parsed, body = split_frontmatter(join_frontmatter(meta, "some body"))
        assert parsed == meta
        assert body == "some body"

    def test_dates_keep_their_type(self):
        """TOML's three date types are exactly BLOC's three kinds of time."""
        meta = {
            "created": datetime(2026, 8, 14, 9, 12, 3, tzinfo=UTC),
            "due": date(2026, 8, 14),
            "start": datetime(2026, 8, 14, 14, 0),
        }
        parsed, _ = split_frontmatter(join_frontmatter(meta, ""))
        assert parsed == meta
        assert parsed["start"].tzinfo is None
        assert parsed["created"].tzinfo is not None

    def test_absent_frontmatter_returns_the_whole_text(self):
        assert split_frontmatter("# Just a note\n\nbody") == ({}, "# Just a note\n\nbody")

    def test_unterminated_fence_is_treated_as_body(self):
        """A hand-edited vault must stay readable mid-keystroke."""
        text = "+++\ntitle = 'half typed'\n\nbody"
        assert split_frontmatter(text) == ({}, text)

    def test_empty_body(self):
        meta, body = split_frontmatter(join_frontmatter({"title": "x"}))
        assert meta == {"title": "x"}
        assert body == ""

    def test_body_containing_the_journal_separator_is_safe(self):
        """
        `+++` rather than `---` precisely so a body carrying the v0.1 journal
        entry separator cannot terminate the frontmatter early.
        """
        body = "first\n\n---\n*09:12*\n\nsecond"
        meta, parsed = split_frontmatter(join_frontmatter({"title": "j"}, body))
        assert meta == {"title": "j"}
        assert parsed == body


class TestFindCheckboxes:
    def test_no_checkbox(self):
        assert find_checkboxes("just a line of prose") == []

    def test_one(self):
        [item] = find_checkboxes("- [ ] Call the dentist")
        assert item.title == "Call the dentist"
        assert item.done is False

    def test_done_marker(self):
        assert find_checkboxes("- [x] Done")[0].done is True
        assert find_checkboxes("- [X] Done")[0].done is True

    def test_recovers_a_concatenated_line(self):
        """
        The shape v0.1 produced on every complete-then-add: the rewrite paths
        dropped the trailing newline, so the next append landed on the same line
        and one task vanished from every reader.
        """
        found = find_checkboxes("- [ ] Bravo - [ ] Charlie")
        assert [item.title for item in found] == ["Bravo", "Charlie"]

    def test_recovers_three(self):
        found = find_checkboxes("- [x] A 2026-08-01 - [ ] B - [ ] C #work")
        assert [item.title for item in found] == ["A", "B", "C"]

    def test_a_marker_inside_a_word_is_not_a_task(self):
        assert find_checkboxes("array-[x]-index notation") == []

    def test_indented_task_is_found(self):
        """`Vault.list_tasks` matched on the raw line, so indented tasks were invisible."""
        assert find_checkboxes("    - [ ] Nested")[0].title == "Nested"


class TestParseCheckbox:
    def test_inbox_format(self):
        """`- [ ] {title}{due} {tags}` — what core/vault.py:77 writes."""
        item = parse_checkbox("Call the dentist 2026-08-01 #health #admin")
        assert item.title == "Call the dentist"
        assert item.due == date(2026, 8, 1)
        assert item.tags == ("health", "admin")

    def test_kanban_format(self):
        """`- [ ] {title}  📅 {due}  #tags  🔥` — what tasks/kanban.py:60 writes."""
        item = parse_checkbox("Ship the thing  📅 2026-08-01  #work  🔥")
        assert item.title == "Ship the thing"
        assert item.due == date(2026, 8, 1)
        assert item.tags == ("work",)
        assert item.priority == "high"

    def test_completed_line_with_both_dates(self):
        """
        `complete_task` appends a stamp after the tags, so a done line can carry
        a due date and a completion date. The last one is the stamp.
        """
        item = parse_checkbox("Alpha 2026-08-01 #work  2026-07-29", done=True)
        assert item.title == "Alpha"
        assert item.due == date(2026, 8, 1)
        assert item.completed == date(2026, 7, 29)

    def test_completed_line_with_one_date_is_a_stamp_not_a_due(self):
        item = parse_checkbox("Alpha #work  2026-07-29", done=True)
        assert item.completed == date(2026, 7, 29)
        assert item.due is None

    def test_a_marked_due_on_a_done_card_stays_a_due(self):
        """A kanban card carries no completion stamp, so 📅 must win."""
        item = parse_checkbox("Ship it  📅 2026-08-01  #work", done=True)
        assert item.due == date(2026, 8, 1)
        assert item.completed is None

    def test_open_line_dates_are_due_dates(self):
        assert parse_checkbox("Alpha 2026-08-01").due == date(2026, 8, 1)

    def test_metadata_is_removed_from_the_title(self):
        """
        v0.1's two `re.sub` calls in autoflight were no-ops against the real
        format, so the flight-strip callsign was built from a polluted title.
        """
        assert parse_checkbox("Alpha 2026-08-01 #work #x 🔥").title == "Alpha"

    def test_duplicate_tags_collapse_in_order(self):
        assert parse_checkbox("A #work #x #work").tags == ("work", "x")

    def test_whitespace_is_normalised(self):
        assert parse_checkbox("  spaced    out   ").title == "spaced out"

    def test_no_metadata(self):
        item = parse_checkbox("plain title")
        assert (item.title, item.due, item.tags, item.priority) == ("plain title", None, (), "")


class TestRenderCheckbox:
    def test_round_trip_full(self):
        item = Checkbox(
            title="Call the dentist",
            done=False,
            due=date(2026, 8, 1),
            tags=("health", "admin"),
        )
        assert find_checkboxes(render_checkbox(item)) == [item]

    def test_round_trip_minimal(self):
        item = Checkbox(title="Plain")
        assert find_checkboxes(render_checkbox(item)) == [item]

    def test_round_trip_completed(self):
        item = Checkbox(
            title="Alpha", done=True, due=date(2026, 8, 1), completed=date(2026, 7, 29)
        )
        assert find_checkboxes(render_checkbox(item)) == [item]

    def test_round_trip_priority(self):
        item = Checkbox(title="Urgent", priority="high", tags=("work",))
        assert find_checkboxes(render_checkbox(item)) == [item]

    def test_shape_matches_the_v01_inbox_writer(self):
        item = Checkbox(title="Alpha", due=date(2026, 8, 1), tags=("work",))
        assert render_checkbox(item) == "- [ ] Alpha 2026-08-01 #work"
