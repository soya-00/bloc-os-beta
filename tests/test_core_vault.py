"""
The filesystem layer, exercised against a real temporary vault.

The lenient-reader tests are the load-bearing ones: they are what makes "new
notes get frontmatter" a change that requires no migration of the notes already
on disk.
"""

from datetime import UTC, date, datetime

import pytest

from bloc.core import clock
from bloc.core.vault import VAULT_VERSION, Vault


@pytest.fixture
def vault(tmp_path):
    v = Vault(tmp_path / "bloc")
    v.ensure()
    return v


class TestRoot:
    def test_explicit_root_wins(self, tmp_path):
        assert Vault(tmp_path).root == tmp_path

    def test_environment_override(self, tmp_path, monkeypatch):
        """Lets the migration dry-run against a copy of a real vault."""
        monkeypatch.setenv("BLOC_HOME", str(tmp_path / "scratch"))
        assert Vault().root == tmp_path / "scratch"

    def test_defaults_under_home(self, monkeypatch, tmp_path):
        monkeypatch.delenv("BLOC_HOME", raising=False)
        monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: tmp_path))
        assert Vault().root == tmp_path / "bloc"

    def test_constructing_creates_nothing(self, tmp_path):
        """Reading a path should not have the side effect of building a vault."""
        Vault(tmp_path / "bloc")
        assert not (tmp_path / "bloc").exists()

    def test_ensure_skips_legacy_directories(self, vault):
        """A fresh vault should not sprout folders for formats it never writes."""
        assert vault.dirs["notes"].is_dir()
        assert vault.dirs["strips"].is_dir()
        assert not vault.dirs["calendar"].exists()
        assert not vault.dirs["boards"].exists()

    def test_legacy_paths_are_still_addressable(self, vault):
        """The migration has to be able to find them."""
        assert vault.dirs["tasks"].name == "tasks"
        assert vault.dirs["boards"] == vault.root / "tasks" / "boards"


class TestVersion:
    def test_absent_reads_as_none(self, vault):
        assert vault.version() is None

    def test_round_trip(self, vault):
        vault.set_version()
        assert vault.version() == VAULT_VERSION

    def test_garbage_reads_as_none_rather_than_raising(self, vault):
        vault.version_file.write_text("not a number\n")
        assert vault.version() is None


class TestWriteNote:
    def test_writes_readable_frontmatter(self, vault):
        path = vault.write_note("Call the dentist", "ring at nine", ("health",))
        note = vault.read_note(path)
        assert note.title == "Call the dentist"
        assert note.body == "ring at nine"
        assert note.tags == ("health",)
        assert note.created.tzinfo is not None

    def test_filename_is_chronological_then_slugged(self, vault):
        with clock.frozen(datetime(2026, 8, 14, 9, 12, tzinfo=UTC)):
            path = vault.write_note("Call the dentist")
        assert path.name.endswith("-call-the-dentist.md")
        assert path.name.startswith("2026-08-14-")

    def test_a_hostile_title_stays_inside_the_notes_directory(self, vault):
        path = vault.write_note("../../etc/passwd")
        assert vault.dirs["notes"] in path.resolve().parents

    def test_a_hostile_title_survives_intact_in_the_document(self, vault):
        """Sanitising the filename must not corrupt the title itself."""
        title = "../../etc/passwd #x 🔥"
        note = vault.read_note(vault.write_note(title))
        assert note.title == title

    def test_two_notes_in_one_minute_are_two_files(self, vault):
        """v0.1 silently overwrote the first."""
        with clock.frozen(datetime(2026, 8, 14, 9, 12, tzinfo=UTC)):
            first = vault.write_note("Same title", "first")
            second = vault.write_note("Same title", "second")
        assert first != second
        assert vault.read_note(first).body == "first"
        assert vault.read_note(second).body == "second"

    def test_no_tags_key_when_there_are_none(self, vault):
        assert vault.read_note(vault.write_note("Bare")).tags == ()

    def test_body_containing_a_fence_survives(self, vault):
        body = "some notes\n\n---\n\nmore notes"
        assert vault.read_note(vault.write_note("t", body)).body == body


class TestReadLegacyNote:
    """
    v0.1's format: `# title`, a bare tag line, then the body — written by
    core/vault.py:43 and parsed by nothing. Reading it means no note migration.
    """

    def make(self, vault, name, text):
        path = vault.dirs["notes"] / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_title_comes_from_the_heading(self, vault):
        path = self.make(vault, "2026-08-14-09-12-old.md", "# Old note\n\n#work\n\nbody")
        assert vault.read_note(path).title == "Old note"

    def test_tags_come_from_the_header_region(self, vault):
        path = self.make(vault, "2026-08-14-09-12-old.md", "# Old\n\n#work #admin\n\nbody")
        assert vault.read_note(path).tags == ("work", "admin")

    def test_created_comes_from_the_filename_stamp(self, vault):
        path = self.make(vault, "2026-08-14-09-12-old.md", "# Old\n\n\nbody")
        assert vault.read_note(path).created == datetime(2026, 8, 14, 9, 12)

    def test_tags_deeper_in_the_body_are_not_collected(self, vault):
        """Scanning the whole document would harvest every # in the prose."""
        text = "# Old\n\n#work\n\nbody\n\n    # a comment\n#notatag"
        path = self.make(vault, "2026-08-14-09-12-old.md", text)
        assert vault.read_note(path).tags == ("work",)

    def test_a_note_with_no_heading_falls_back_to_the_filename(self, vault):
        path = self.make(vault, "loose-note.md", "no heading here")
        assert vault.read_note(path).title == "loose-note"

    def test_a_note_with_no_stamp_has_no_created(self, vault):
        path = self.make(vault, "loose-note.md", "# T\n\nbody")
        assert vault.read_note(path).created is None

    def test_missing_file_reads_as_none(self, vault):
        assert vault.read_note(vault.dirs["notes"] / "nope.md") is None

    def test_unreadable_file_reads_as_none(self, vault):
        path = vault.dirs["notes"] / "binary.md"
        path.write_bytes(b"\xff\xfe\x00")
        assert vault.read_note(path) is None


class TestListNotes:
    def test_newest_first(self, vault):
        import os

        older = vault.write_note("Older")
        newer = vault.write_note("Newer")
        os.utime(older, (0, 0))
        assert vault.list_notes()[0] == newer

    def test_empty_vault(self, vault):
        assert vault.list_notes() == []


class TestJournal:
    def test_creates_the_day(self, vault):
        path = vault.append_journal("first thought", day=date(2026, 8, 14))
        assert path.name == "2026-08-14.md"
        assert "first thought" in path.read_text()
        assert path.read_text().startswith("# Journal — 2026-08-14")

    def test_appends_without_rewriting(self, vault):
        vault.append_journal("first", day=date(2026, 8, 14))
        path = vault.append_journal("second", day=date(2026, 8, 14))
        text = path.read_text()
        assert "first" in text
        assert "second" in text
        assert text.count("# Journal") == 1
        assert text.count("---") == 1

    def test_defaults_to_today(self, vault):
        with clock.frozen(datetime(2026, 8, 14, 12, 0, tzinfo=UTC)):
            path = vault.append_journal("x")
            assert path.stem == clock.today().isoformat()


class TestSearch:
    def test_finds_a_line(self, vault):
        vault.write_note("Dentist", "ring at nine")
        [hit] = vault.search("ring at")
        assert hit.text == "ring at nine"
        assert hit.line > 0

    def test_is_case_insensitive(self, vault):
        vault.write_note("Dentist", "Ring At Nine")
        assert vault.search("ring at nine")

    def test_empty_query_returns_nothing(self, vault):
        vault.write_note("Dentist", "body")
        assert vault.search("") == []

    def test_archive_directory_is_skipped(self, vault):
        (vault.dirs["archive"] / "old.md").write_text("secret content")
        assert vault.search("secret content") == []

    def test_a_note_named_archive_is_still_searched(self, vault):
        """
        v0.1 tested `"archive" in str(path)` against the whole path, so any note
        whose own name contained the word was silently invisible.
        """
        vault.write_note("archive plan", "restructure the shelves")
        assert vault.search("restructure the shelves")

    def test_one_unreadable_file_does_not_abort_the_search(self, vault):
        """v0.1 raised UnicodeDecodeError and lost every other result."""
        (vault.dirs["notes"] / "binary.md").write_bytes(b"\xff\xfe\x00")
        vault.write_note("Good", "findable content")
        assert vault.search("findable content")

    def test_limit_is_honoured(self, vault):
        vault.write_note("Many", "\n".join("needle" for _ in range(50)))
        assert len(vault.search("needle", limit=10)) == 10
