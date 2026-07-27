# Decisions

A running log, newest last. One entry per working session: what changed, what
was chosen over what and why, and the next obvious step.

The point is resumability. Work on this project happens occasionally, and the
expensive part of picking it back up is reconstructing intent — not re-reading
code.

---

## S1 — Repository hygiene, packaging, package skeleton

**Date:** 2026-07-27
**Milestone:** Month 1, week 1

### What changed

- Added `.gitignore` and untracked `venv/` and `__pycache__/`.
- Added `pyproject.toml`: metadata, pinned dependencies, `[pi]` and `[dev]`
  extras, ruff and pytest configuration, and a `bloc` console entry point.
- Created the `bloc/` package skeleton with the layering documented in each
  `__init__.py`.
- Added `tests/` with skeleton smoke tests.

### Why

A fresh clone could not boot. There was no dependency manifest of any kind, and
the committed `venv/` was Windows-only *and* incomplete — `tomli` was missing,
and `core/config.py` imports it at module scope, so `main.py` died on line 11.
Reproducing the environment meant reading every import statement in the tree.

364 of 413 tracked files were `venv/`, so every diff was unreadable.

### Choices made

- **Untracked the venv rather than purging it from history.** A `filter-repo`
  rewrite would reclaim ~45 MB of `.git`, but this is a personal repository and
  the cost is a whole session for no functional gain. The working directory copy
  is left on disk, just no longer tracked; it can be deleted safely at any time.

- **Dropped `tomli` in favour of the standard library.** `tomllib` has been in
  the standard library since Python 3.11, so only a TOML *writer* is an actual
  dependency. `requires-python = ">=3.11"` covers Raspberry Pi OS Bookworm
  (3.11) and Trixie (3.13). One less dependency, and it removes the exact import
  that broke a fresh clone.

- **Pinned `colorama` and `faster-whisper` to observed versions; floors for the
  rest.** Those two were verifiable from the committed venv metadata. Inventing
  exact pins for packages that were never installed would be a fake lockfile.

- **Hardware dependencies are a `[pi]` extra, not core.** They cannot install on
  a laptop, and the HAL exists precisely so the same source runs on both.
  `gpiozero` + `lgpio`, **not `RPi.GPIO`** — the Pi 5's RP1 southbridge changed
  the GPIO interface and `RPi.GPIO` does not work there. This trips up anyone
  following Pi 4-era material.

- **Ruff excludes the legacy modules for now.** They are being replaced
  subsystem by subsystem; linting code scheduled for deletion is noise. Each
  session that ports a subsystem removes its entry from `extend-exclude`, so the
  exclusion list shrinks to nothing rather than becoming permanent.

  Worth noting that the selected rule set would have caught two of the bugs
  already in the tree: `F` (pyflakes) catches the undefined `result` in
  `voice/handler.py:95`, and `B` (bugbear) catches the mutable default `tags:
  list = []` in `core/vault.py:34`.

- **The new entry point exits non-zero with an explanatory message** instead of
  pretending to work. The rebuild is a strangler-fig migration; `main.py` stays
  the working entry point until the boot sequence is ported in S7.

### Not done, deliberately

- No behaviour changes. No bug fixes. The eleven known defects are scheduled
  into the sessions that rewrite their subsystems, so each fix lands with tests
  rather than as a patch to code about to be deleted.

### Next

**S2** — `bloc/ui/`: port `theme.py`, `vocab.py`, `keys.py`, `widgets.py`. The
aesthetic layer becomes canonical, one key reader replaces eight copies and
fixes all three Linux-only input bugs, and the three divergent `V` vocabulary
dicts merge into one.
