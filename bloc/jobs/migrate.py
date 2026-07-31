"""
The one-shot that turns three legacy formats into strips.

    python -m bloc.jobs.migrate            # dry run — prints, writes nothing
    python -m bloc.jobs.migrate --apply    # writes

**This is the single most dangerous operation in the rebuild.** It moves live
personal data between formats, and everything about its shape is chosen so a bug
costs a confusing afternoon rather than a vault.

## Plan, then apply

`plan()` walks the vault and returns everything it *would* do, touching nothing.
`apply()` is a dumb executor over that result. The dry-run and the real run are
therefore **the same computation**, differing only in whether `apply` is called
— a preview that re-derives its own answer is a preview that can disagree with
the thing it previews.

## The order of operations, and why

1. **Dry run is the default.** Writing takes `--apply`: a flag is a decision you
   can see afterwards in your shell history, which an interactive prompt is not.
2. **Refuse a vault that is already migrated.** A matching `.bloc-version` exits
   cleanly with nothing to do, which is what makes re-running a no-op.
3. **Refuse an unstamped vault that already has strips.** That is a state this
   tool did not create, and guessing at it risks duplicating every record.
4. **Strips are written before originals move.** If the write half fails, the
   legacy vault is untouched and the old shell still works.
5. **Originals are *moved*, never deleted** — to `archive/pre-unification/`,
   keeping their relative layout.
6. **`.bloc-version` is stamped last.** It is the commit point: the stamp means
   every earlier step finished.

What none of that protects against is this tool mangling content on the way
through, which is why the dry-run output ends by telling you to `tar` the vault
somewhere else first. The archive move guards against loss, not against a buggy
migrator.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from bloc.core.strips import BAY_ORDER, Status, StripStore
from bloc.core.vault import VAULT_VERSION, Vault
from bloc.jobs.legacy import Fault, Proposal, read_all, sources_for

#: Where originals go. Moved rather than deleted, and never written into by
#: anything else, so the pre-migration vault stays reconstructable by hand.
ARCHIVE = "pre-unification"

#: Printed at the end of every dry run. The one risk the tool cannot mitigate.
TAR_WARNING = (
    "take a copy first:  tar czf ~/bloc-backup.tgz -C ~ bloc\n"
    "  the archive move protects against loss, not against a buggy migrator"
)


@dataclass(frozen=True)
class MigrationPlan:
    """Everything the migration would do. Computed without touching disk."""

    vault: Vault
    #: Proposals paired with the callsign each would be given, in allocation order.
    assignments: list[tuple[str, Proposal]] = field(default_factory=list)
    faults: list[Fault] = field(default_factory=list)
    sources: list[Path] = field(default_factory=list)
    #: Set when the vault is already migrated, or is in a state this tool did
    #: not create. Non-empty means `apply()` refuses.
    blocked: str = ""

    @property
    def total(self) -> int:
        return len(self.assignments)

    def counts(self) -> dict[str, int]:
        """How many strips came from each legacy format."""
        tally: dict[str, int] = {"inbox": 0, "board": 0, "agenda": 0}
        for _, proposal in self.assignments:
            tally[proposal.kind] += 1
        return tally


# ── planning ──────────────────────────────────────────────


def plan(vault: Vault | None = None) -> MigrationPlan:
    """
    Work out the whole migration without writing anything.

    Callsigns are allocated here rather than at write time so the dry-run shows
    the real ids. Allocation starts from `next_id()`, so a vault that already
    holds strips is extended rather than collided with.
    """
    vault = vault or Vault()
    store = StripStore(vault)

    proposals, faults = read_all(vault)
    sources = sources_for(vault)

    blocked = _blocked_reason(vault, store, proposals)

    number = _first_number(store)
    assignments = [
        (f"BLK-{number + offset:03d}", proposal) for offset, proposal in enumerate(proposals)
    ]

    return MigrationPlan(
        vault=vault,
        assignments=assignments,
        faults=faults,
        sources=sources,
        blocked=blocked,
    )


def _first_number(store: StripStore) -> int:
    from bloc.core.strips import ID_PATTERN

    return int(ID_PATTERN.match(store.next_id()).group(1))


def _blocked_reason(vault: Vault, store: StripStore, proposals: list[Proposal]) -> str:
    """Why `apply()` must refuse, or `""` if it may proceed."""
    version = vault.version()
    if version is not None and version >= VAULT_VERSION:
        return f"vault is already at format version {version} — nothing to do"
    if version is None and store.dir.is_dir() and any(store.dir.glob("*.md")):
        return (
            f"{store.dir} already contains strips but the vault carries no version stamp. "
            "This is not a state the migration created; resolve it by hand rather than "
            "risking duplicate records."
        )
    if not proposals:
        return "no legacy tasks, cards or blocks found — nothing to migrate"
    return ""


# ── applying ──────────────────────────────────────────────


def apply(plan: MigrationPlan) -> int:
    """
    Execute a plan. Returns the number of strips written.

    Raises `RuntimeError` if the plan is blocked — callers check `plan.blocked`
    first, and this is the backstop for the ones that forget.
    """
    if plan.blocked:
        raise RuntimeError(plan.blocked)

    vault = plan.vault
    vault.ensure()
    store = StripStore(vault)

    written = 0
    for strip_id, proposal in plan.assignments:
        store.write(_to_strip(strip_id, proposal))
        written += 1

    _archive(vault, plan.sources)
    vault.set_version(VAULT_VERSION)
    return written


def _to_strip(strip_id: str, proposal: Proposal):
    """Build the record. `created` is now — the legacy formats record no birth time."""
    from bloc.core import clock
    from bloc.core.strips import Strip

    return Strip(
        id=strip_id,
        title=proposal.title,
        created=clock.now(),
        body=proposal.body,
        **proposal.to_fields(),
    )


def _archive(vault: Vault, sources: list[Path]) -> None:
    """
    Move the originals under `archive/pre-unification/`, keeping their layout.

    `tasks/inbox.md` lands at `archive/pre-unification/tasks/inbox.md`, so what
    came from where stays obvious a year later. A destination that somehow
    exists is never overwritten — the whole point of this directory is that it
    is the copy of last resort.
    """
    root = vault.dirs["archive"] / ARCHIVE
    for source in sources:
        if not source.is_file():
            continue
        relative = source.relative_to(vault.root)
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination = _free_name(destination)
        shutil.move(str(source), str(destination))


def _free_name(path: Path) -> Path:
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


# ── printing ──────────────────────────────────────────────


def render(plan: MigrationPlan, applied: bool = False) -> str:
    """
    The diff.

    Two properties this output has to keep, because they are what the
    verification step checks: **every source record appears exactly once**, and
    **anything a reader could not understand appears under WARNINGS** rather
    than being dropped. A skipped line that prints nothing is how a migration
    loses data while reporting success.
    """
    lines: list[str] = []

    if plan.blocked:
        return f"BLOC MIGRATION\n\n  {plan.blocked}\n"

    grouped: dict[Path, list[tuple[str, Proposal]]] = {}
    for strip_id, proposal in plan.assignments:
        grouped.setdefault(proposal.source, []).append((strip_id, proposal))

    lines.append("BLOC MIGRATION")
    for source, entries in grouped.items():
        lines.append("")
        lines.append(f"{_heading(entries[0][1], source, plan.vault)}")
        for strip_id, proposal in entries:
            lines.append(f"  {strip_id}  {proposal.status.value:<8} {_describe(proposal)}")

    if plan.faults:
        lines.append("")
        lines.append("WARNINGS")
        for fault in plan.faults:
            where = f"{_relative(fault.source, plan.vault)}"
            if fault.line:
                where += f":{fault.line}"
            lines.append(f"  {where}  {fault.message}")

    tally = plan.counts()
    lines.append("")
    lines.append(
        f"  {tally['inbox']} tasks · {tally['board']} cards · {tally['agenda']} blocks"
        f"  →  {plan.total} strips"
    )
    lines.append(f"  {len(plan.sources)} source files move to archive/{ARCHIVE}/")

    if applied:
        lines.append(f"  written. vault stamped at format version {VAULT_VERSION}")
    else:
        lines.append("")
        lines.append("  nothing has been written — re-run with --apply")
        lines.append(f"  {TAR_WARNING}")

    return "\n".join(lines) + "\n"


def _heading(proposal: Proposal, source: Path, vault: Vault) -> str:
    label = {"inbox": "INBOX", "board": f"BOARD  {proposal.board}", "agenda": "AGENDA"}
    return f"{label[proposal.kind]:<20} {_relative(source, vault)}"


def _relative(path: Path, vault: Vault) -> str:
    try:
        return str(path.relative_to(vault.root))
    except ValueError:
        return str(path)


def _describe(proposal: Proposal) -> str:
    """The right-hand detail column — whatever this record actually carries."""
    parts = [proposal.title[:38]]
    if proposal.due:
        parts.append(f"due {proposal.due}")
    if proposal.scheduled_start and proposal.scheduled_end:
        parts.append(
            f"{proposal.scheduled_start:%H:%M}–{proposal.scheduled_end:%H:%M}"
        )
    if proposal.completed:
        parts.append(f"completed {proposal.completed:%Y-%m-%d}")
    if proposal.column:
        note = f'column "{proposal.column}"'
        if proposal.unmapped_column:
            note += "  (unmapped → queued)"
        parts.append(note)
    if proposal.tags:
        parts.append(" ".join(f"#{tag}" for tag in proposal.tags))
    if proposal.priority:
        parts.append(f"!{proposal.priority}")
    if proposal.nested_tasks:
        parts.append(f"({proposal.nested_tasks} nested tasks kept in body)")
    return "  ".join(parts)


def summarise(store: StripStore) -> str:
    """Bay counts after a migration — the shape the objectives screen will show."""
    strips = store.all()
    counts = {status: sum(1 for s in strips if s.status is status) for status in BAY_ORDER}
    scrubbed = sum(1 for s in strips if s.status is Status.SCRUBBED)
    parts = [f"{status.value} {count}" for status, count in counts.items()]
    if scrubbed:
        parts.append(f"scrubbed {scrubbed}")
    return "  ".join(parts)


# ── entry point ───────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bloc.jobs.migrate",
        description="Migrate inbox.md, boards/*.md and calendar/*.md into strips/.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write. Without this, nothing is modified.",
    )
    parser.add_argument(
        "--home",
        metavar="DIR",
        help="vault root, overriding BLOC_HOME. Use a copy to rehearse.",
    )
    args = parser.parse_args(argv)

    vault = Vault(args.home) if args.home else Vault()
    result = plan(vault)

    if result.blocked:
        sys.stdout.write(render(result))
        # An already-migrated vault is a successful no-op, not a failure —
        # re-running has to be safe to put in a script.
        return 0

    if not args.apply:
        sys.stdout.write(render(result))
        return 0

    apply(result)
    sys.stdout.write(render(result, applied=True))
    sys.stdout.write(f"  bays: {summarise(StripStore(vault))}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
