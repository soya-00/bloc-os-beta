"""
The migration — the one session that moves live personal data between formats.

These tests are weighted towards the failure modes rather than the happy path,
because the happy path is the cheap half. What matters is that a blocked vault
refuses, that a crash halfway leaves the old system working, that re-running
changes nothing, and that every original is recoverable byte-for-byte
afterwards.
"""

from datetime import date, datetime

import pytest

from bloc.core.strips import Status, StripStore
from bloc.core.vault import VAULT_VERSION, Vault
from bloc.jobs import migrate
from bloc.jobs.migrate import apply, plan, render

INBOX = """# Inbox

- [ ] Call the dentist 2026-08-14 #health
- [x] Book the flights 2026-07-05 #travel  2026-07-11
- [ ] Bravo - [ ] Charlie
"""

BOARD = """# Admin

## In Progress
- [ ] Rewrite the parser  📅 2026-09-01  #code  🔥

## Done
- [x] File the tax return
"""

AGENDA = """# AGENDA · WEDNESDAY 29 JULY 2026

## 09:00 → 10:30 | DEEP WORK
> Build the RADAR module

## 14:00 → 15:00 | ADMIN ✓
"""


@pytest.fixture
def vault(tmp_path):
    """A legacy vault: four tasks, two cards, two blocks — eight strips."""
    v = Vault(tmp_path)
    for path, text in (
        (v.dirs["tasks"] / "inbox.md", INBOX),
        (v.dirs["boards"] / "admin.md", BOARD),
        (v.dirs["calendar"] / "2026-07-29.md", AGENDA),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return v


class TestPlanning:
    def test_every_record_is_accounted_for(self, vault):
        result = plan(vault)
        assert result.total == 8
        assert result.counts() == {"inbox": 4, "board": 2, "agenda": 2}

    def test_callsigns_are_contiguous_across_all_three_sources(self, vault):
        ids = [strip_id for strip_id, _ in plan(vault).assignments]
        assert ids == [f"BLK-{n:03d}" for n in range(1, 9)]

    def test_planning_writes_nothing(self, vault):
        plan(vault)
        assert not (vault.root / "strips").exists()
        assert (vault.dirs["tasks"] / "inbox.md").exists()
        assert vault.version() is None

    def test_two_plans_agree(self, vault):
        """A dry-run that cannot predict the real run's ids is not a preview."""
        first = [(i, p.title) for i, p in plan(vault).assignments]
        assert first == [(i, p.title) for i, p in plan(vault).assignments]

    def test_an_empty_vault_is_blocked_with_nothing_to_do(self, tmp_path):
        assert "nothing to migrate" in plan(Vault(tmp_path)).blocked

    def test_an_already_migrated_vault_is_blocked(self, vault):
        apply(plan(vault))
        assert "already at format version" in plan(vault).blocked

    def test_an_unstamped_vault_holding_strips_is_blocked(self, vault):
        """
        Strips with no version stamp is a state this tool did not create.
        Guessing at it risks writing a second copy of every record.
        """
        store = StripStore(vault)
        store.dir.mkdir(parents=True, exist_ok=True)
        store.create("A strip that was already here")
        assert "not a state the migration created" in plan(vault).blocked


class TestApplying:
    def test_strips_are_written_and_read_back_cleanly(self, vault):
        assert apply(plan(vault)) == 8
        store = StripStore(vault)
        strips = store.all()
        assert len(strips) == 8
        # The migration must never emit a document its own parser rejects.
        assert store.errors == []

    def test_the_three_kinds_of_time_survive(self, vault):
        apply(plan(vault))
        by_title = {s.title: s for s in StripStore(vault).all()}

        assert by_title["Call the dentist"].due == date(2026, 8, 14)
        assert isinstance(by_title["Call the dentist"].due, date)
        assert not isinstance(by_title["Call the dentist"].due, datetime)

        assert by_title["Call the dentist"].created.tzinfo is not None
        assert by_title["Book the flights"].completed.tzinfo is not None

        block = by_title["DEEP WORK"]
        assert block.scheduled_start == datetime(2026, 7, 29, 9, 0)
        assert block.scheduled_start.tzinfo is None

    def test_statuses_land_in_the_right_bays(self, vault):
        apply(plan(vault))
        by_title = {s.title: s.status for s in StripStore(vault).all()}
        assert by_title["Call the dentist"] is Status.QUEUED
        assert by_title["Book the flights"] is Status.DONE
        assert by_title["Rewrite the parser"] is Status.ACTIVE
        assert by_title["DEEP WORK"] is Status.QUEUED
        assert by_title["ADMIN"] is Status.DONE

    def test_the_version_is_stamped(self, vault):
        apply(plan(vault))
        assert vault.version() == VAULT_VERSION

    def test_applying_a_blocked_plan_raises(self, tmp_path):
        with pytest.raises(RuntimeError):
            apply(plan(Vault(tmp_path)))

    def test_rerunning_is_a_no_op(self, vault):
        apply(plan(vault))
        before = sorted(path.name for path in StripStore(vault).dir.glob("*.md"))

        second = plan(vault)
        assert second.blocked
        with pytest.raises(RuntimeError):
            apply(second)

        after = sorted(path.name for path in StripStore(vault).dir.glob("*.md"))
        assert before == after


class TestOriginalsSurvive:
    def test_sources_move_to_the_archive_keeping_their_layout(self, vault):
        apply(plan(vault))
        root = vault.dirs["archive"] / "pre-unification"
        assert (root / "tasks" / "inbox.md").is_file()
        assert (root / "tasks" / "boards" / "admin.md").is_file()
        assert (root / "calendar" / "2026-07-29.md").is_file()

    def test_archived_content_is_byte_identical(self, vault):
        apply(plan(vault))
        archived = vault.dirs["archive"] / "pre-unification" / "tasks" / "inbox.md"
        assert archived.read_text(encoding="utf-8") == INBOX

    def test_originals_are_moved_not_copied(self, vault):
        apply(plan(vault))
        assert not (vault.dirs["tasks"] / "inbox.md").exists()

    def test_nothing_is_ever_unlinked(self, vault):
        """Every source file still exists somewhere after the migration."""
        sources = plan(vault).sources
        apply(plan(vault))
        root = vault.dirs["archive"] / "pre-unification"
        for source in sources:
            assert (root / source.relative_to(vault.root)).is_file()


class TestFailureLeavesTheOldSystemWorking:
    def test_a_crash_during_the_archive_move_keeps_the_legacy_vault_readable(
        self, vault, monkeypatch
    ):
        """
        Strips are written *before* originals move, so a failure in the second
        half leaves the legacy vault intact and the old shell still working.
        That ordering is the whole reason the strangler-fig promise survives a
        bad migration run.
        """

        def explode(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(migrate.shutil, "move", explode)

        with pytest.raises(OSError):
            apply(plan(vault))

        inbox = vault.dirs["tasks"] / "inbox.md"
        assert inbox.is_file()
        assert inbox.read_text(encoding="utf-8") == INBOX
        # And the vault is not stamped, so a later run still knows there is work.
        assert vault.version() is None

    def test_an_interrupted_run_can_be_replanned(self, vault, monkeypatch):
        monkeypatch.setattr(migrate.shutil, "move", lambda *a, **k: None)
        apply(plan(vault))
        # Version was stamped, so the vault now correctly reports nothing to do
        # rather than offering to migrate the same records twice.
        assert plan(vault).blocked


class TestRendering:
    def test_every_strip_appears_exactly_once(self, vault):
        result = plan(vault)
        text = render(result)
        for strip_id, _ in result.assignments:
            assert text.count(strip_id) == 1

    def test_faults_are_printed_rather_than_dropped(self, vault):
        text = render(plan(vault))
        assert "WARNINGS" in text
        assert "H1 concatenation" in text

    def test_a_dry_run_says_it_wrote_nothing_and_asks_for_a_backup(self, vault):
        text = render(plan(vault))
        assert "nothing has been written" in text
        assert "tar" in text

    def test_an_applied_run_says_so(self, vault):
        result = plan(vault)
        apply(result)
        assert "written" in render(result, applied=True)

    def test_a_blocked_plan_renders_its_reason_and_nothing_else(self, tmp_path):
        text = render(plan(Vault(tmp_path)))
        assert "nothing to migrate" in text
        assert "BLK-" not in text

    def test_source_counts_are_reported(self, vault):
        text = render(plan(vault))
        assert "4 tasks · 2 cards · 2 blocks" in text


class TestEntryPoint:
    def test_a_dry_run_exits_zero_and_writes_nothing(self, vault, capsys):
        assert migrate.main(["--home", str(vault.root)]) == 0
        assert "nothing has been written" in capsys.readouterr().out
        assert vault.version() is None

    def test_apply_writes(self, vault, capsys):
        assert migrate.main(["--home", str(vault.root), "--apply"]) == 0
        assert "bays:" in capsys.readouterr().out
        assert len(StripStore(vault).all()) == 8

    def test_rerunning_the_command_exits_zero(self, vault, capsys):
        """Safe to leave in a script: an already-migrated vault is success, not failure."""
        migrate.main(["--home", str(vault.root), "--apply"])
        capsys.readouterr()
        assert migrate.main(["--home", str(vault.root), "--apply"]) == 0
        assert "nothing to do" in capsys.readouterr().out
