"""
Filesystem primitives.

The slug tests are the ones that matter: v0.1's two slug functions replaced
spaces and stopped, so a board named `A/B` resolved outside its own directory.
"""

import os

import pytest

from bloc.core.files import atomic_write_text, read_text, slugify, unique_path


class TestAtomicWrite:
    def test_writes_and_overwrites(self, tmp_path):
        target = tmp_path / "note.md"
        atomic_write_text(target, "first")
        atomic_write_text(target, "second")
        assert target.read_text() == "second"

    def test_creates_missing_parents(self, tmp_path):
        target = tmp_path / "a" / "b" / "c.md"
        atomic_write_text(target, "x")
        assert target.read_text() == "x"

    def test_a_failed_write_leaves_the_original_intact(self, tmp_path, monkeypatch):
        """The whole point: a torn write must not cost the existing file."""
        target = tmp_path / "agenda.md"
        atomic_write_text(target, "the whole day")

        def boom(*args, **kwargs):
            raise OSError("power loss")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            atomic_write_text(target, "truncated")

        assert target.read_text() == "the whole day"

    def test_a_failed_write_leaves_no_temp_file_behind(self, tmp_path, monkeypatch):
        target = tmp_path / "agenda.md"
        atomic_write_text(target, "original")

        monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError()))
        with pytest.raises(OSError):
            atomic_write_text(target, "new")

        assert list(tmp_path.iterdir()) == [target]

    def test_temp_file_is_made_in_the_destination_directory(self, tmp_path):
        """
        os.replace is only atomic within one filesystem, so the temp file cannot
        live in the system temp directory.
        """
        seen = []
        target = tmp_path / "deep" / "note.md"
        target.parent.mkdir()

        import tempfile as tempfile_module

        from bloc.core import files

        real = tempfile_module.mkstemp

        def spy(*args, **kwargs):
            seen.append(kwargs.get("dir"))
            return real(*args, **kwargs)

        files.tempfile.mkstemp = spy
        try:
            atomic_write_text(target, "x")
        finally:
            files.tempfile.mkstemp = real

        assert seen == [target.parent]

    def test_newlines_are_not_translated(self, tmp_path):
        target = tmp_path / "x.md"
        atomic_write_text(target, "a\nb\n")
        assert target.read_bytes() == b"a\nb\n"


class TestReadText:
    def test_missing_file_is_none_not_an_exception(self, tmp_path):
        assert read_text(tmp_path / "nope.md") is None

    def test_directory_is_none(self, tmp_path):
        assert read_text(tmp_path) is None

    def test_non_utf8_is_none(self, tmp_path):
        """One bad file aborted v0.1's entire search with a traceback."""
        target = tmp_path / "binary.md"
        target.write_bytes(b"\xff\xfe\x00garbage")
        assert read_text(target) is None

    def test_reads_normal_content(self, tmp_path):
        target = tmp_path / "x.md"
        target.write_text("hello")
        assert read_text(target) == "hello"


class TestSlugify:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Call the dentist", "call-the-dentist"),
            ("A/B", "a-b"),
            ("../../etc/passwd", "etc-passwd"),
            ("..", "untitled"),
            ("", "untitled"),
            ("   ", "untitled"),
            ("#### ", "untitled"),
            ("Ship #v2 🔥", "ship-v2"),
            ("Café résumé", "cafe-resume"),
            ("C:\\Windows\\system32", "c-windows-system32"),
            ("multiple   spaces", "multiple-spaces"),
            ("--leading--and--trailing--", "leading-and-trailing"),
        ],
    )
    def test_sanitises(self, raw, expected):
        assert slugify(raw) == expected

    @pytest.mark.parametrize("dangerous", ["/", "\\", "..", ":", "\x00", "\n", "*", "?"])
    def test_no_dangerous_character_survives(self, dangerous):
        assert dangerous not in slugify(f"a{dangerous}b")

    def test_result_never_escapes_its_directory(self, tmp_path):
        """The v0.1 bug, stated as a property."""
        target = tmp_path / f"{slugify('../../../etc/passwd')}.md"
        assert tmp_path in target.resolve().parents

    def test_length_is_capped(self):
        assert len(slugify("word " * 100)) <= 40

    def test_cap_does_not_leave_a_trailing_hyphen(self):
        assert not slugify("a" * 39 + " bbbb").endswith("-")


class TestUniquePath:
    def test_first_call_is_the_plain_name(self, tmp_path):
        assert unique_path(tmp_path, "note").name == "note.md"

    def test_collisions_get_numbered(self, tmp_path):
        (tmp_path / "note.md").touch()
        assert unique_path(tmp_path, "note").name == "note-2.md"
        (tmp_path / "note-2.md").touch()
        assert unique_path(tmp_path, "note").name == "note-3.md"

    def test_never_returns_an_existing_path(self, tmp_path):
        for _ in range(5):
            unique_path(tmp_path, "note").touch()
        assert len(list(tmp_path.iterdir())) == 5
