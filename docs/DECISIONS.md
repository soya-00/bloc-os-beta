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

---

## D1 — Design decisions: interaction model, object model, DEBRIEF

**Date:** 2026-07-28
**No code.** Four decisions taken before S2, because each one determines the
shape of code written in the weeks after it.

### 1. Interaction model — the MFD

The surface was 14 top-level commands plus 40+ per-screen bindings with no shared
idiom. The count was never the real problem; flat access is fast, and an
instrument panel is supposed to have buttons. The real problems were:

- **The same key meant different things with no visible legend.** `f` was
  "traffic" at top level and "filter ground traffic" in radar; `s` was "settings"
  and "toggle scope view"; `k` was "mission boards" and "scroll up"; `n` was "new
  note" and "new board"; `a` was "agenda" and "add card".
- **Navigation was verb-first.** `l`/`c`/`d` were three top-level keys for one
  screen — `do_list_tasks`, `do_complete_task` and `do_delete_task` each printed
  the same list and asked for a number.
- **14 destinations shared no state.**

Adopting the avionics multi-function display: a home *status* page rather than a
launcher, four modes (OBJECTIVES · AGENDA · TRAFFIC · SYSTEMS), contextual soft
keys along the bottom, and global keys that work from every screen.

**The load-bearing part: the framework owns the key loop and apps declare soft
keys as data.** That is what makes the legend render itself and global keys work
everywhere without each app cooperating. It is also why this had to be settled
before `bloc/ui/screen.py` exists.

Rejected: keeping flat commands and only fixing the collisions. Cheaper, but it
addresses the confusion without addressing the incoherence.

**A free win found while deciding:** `IntentParser.parse()` takes a `str`. The
natural-language layer already handles tasks, notes, journal, listing, search and
agenda blocks — it is simply wired only to the microphone, behind a modal screen.
Exposing it as a global typed command line absorbs "new note", "new task" and
search almost for free, and makes voice an *input method* rather than a
destination.

**Same design as the GPIO panel.** Physical buttons under a screen with labels
above them *is* an MFD, so `hal/controls_gpio.py` will need no app to know it
exists.

### 2. Object model — full unification on the flight strip

There were two task systems that could not talk: `inbox.md` (via `t`/`l`/`c`/`d`)
and `boards/*.md` (via `k`), with no path between them. Autoflight rendered only
`inbox.md`, so board work was invisible to the best screen in the project. Three
time concepts — agenda blocks, pulse sessions, task due dates — answered one
question with three unrelated records.

**The unifying concept was already in the codebase.** In ATC a flight strip
carries a callsign, times and a status, and moves between bays as the flight
progresses. That is simultaneously a kanban card, an agenda block and a task.
`ui/autoflight.py` already renders tasks as strips with INCOMING / ACTIVE /
LANDED. The metaphor was right; the data model had not caught up.

One record — id, title, status, optional board/column, optional scheduled
start/end, due, tags, priority, timestamps, body. Four views over one store:
board groups by column, agenda filters by scheduled date, flight strips show
today by status, objectives is a flat list.

**Storage: one file per strip** in `~/bloc/strips/` with TOML frontmatter.
Chosen over a single collection file for atomic per-record writes (no more
full-file rewrites as in `AgendaFile.save()`), clean git history, and equal
editability in any editor.

Rejected: a unified *read* layer over the existing three stores. Reversible and
much cheaper, but it leaves three formats and three parsers to keep in sync — and
format drift is what produced the `**due:**` mismatch between
`ui/autoflight.py:262` and `core/vault.py:77` in the first place.

**Cost, accepted:** three extra sessions and a migration of live data.

### 3. New feature — DEBRIEF

Record a 30-second-to-2-minute ramble; transcribe it; extract actionable to-dos;
track recurring emotional and productivity signals over time.

The aviation naming is exact rather than decorative: a post-flight *debrief* is
this, and *trend monitoring* is a real discipline — tracking parameters across
many flights to detect drift no single flight reveals.

Four things make it a separate subsystem from the existing `v` command:

- **Capture differs.** `record_until_silence()` stops after 1.5s of silence,
  which is correct for a command and wrong for a ramble where you pause to think.
- **Transcription must be asynchronous.** Two minutes through faster-whisper on
  Pi CPU is too slow to sit and watch. This is also the strongest argument for
  the NPU anywhere in the project.
- **Extraction from prose is not intent matching.** The existing parser matches
  whole utterances against command patterns. A ramble needs sentence
  segmentation and actionability scoring across *every* sentence, returning
  ranked candidates rather than first-match-wins. The seed exists —
  `voice/intent.py:32` already has `i need to` / `i have to` / `remember to`.
- **Extraction proposes; it never commits.** Candidates go to a review screen —
  accept, edit or reject. **The rule: precision over recall.** A missed to-do
  costs one item; a hallucinated one costs trust in the whole list, and a task
  list you do not trust is dead.

**The genuinely novel part** is correlating what you *said* with what you *did*.
The vault already holds the objective half — completed strips with dates, pulse
session logs, agenda adherence. Nothing else in the system has both halves.

Labelled honestly in the UI as lexicon frequency plus correlation, not sentiment
analysis. Cloud LLM extraction rejected outright: debriefs are the most personal
data BLOC will hold and must never leave the device. Audio discarded by default
(`keep_audio = false`); the transcript is the artifact.

### 4. Schedule — compressed to 24 sessions, deadline unchanged

Adding DEBRIEF and keeping the peripherals in scope, with a fixed four-month
deadline and four unavailable weeks, means **two sessions per week across 12
working weeks** — roughly double the original pace.

The unavailable periods (last two weeks of month 2, first two of month 3) are
**adjacent**, forming one four-week dead zone. Two rules follow: the migration
must not straddle it, and whatever ships in week 6 must be usable unattended for
a month.

**The scheduling insight that shaped everything:** DEBRIEF's recorder ships in
week 6, a ramble is recorded daily through the dead zone, and week 11 begins with
~28 real debriefs — the corpus extraction needs. Extraction quality is entirely a
function of testing against real rambles rather than invented ones, so the four
weeks that cannot be coded are exactly the four weeks that should be spent
collecting data. The constraint costs nothing and buys the feature its test set.
Hardware is ordered to arrive in the same window.

Cut order is decided in advance so it never has to be improvised: e-ink → GPIO
panel → TREND MONITOR (fold into home) → printer. Never cut: the migration, the
Autoflight port, or extraction.

### Next

**S2** as above, then **S3** — the MFD contract in `bloc/ui/screen.py`.
