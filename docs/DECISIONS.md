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

---

## D2 — Schedule review: a sequencing bug and three shape fixes

**Date:** 2026-07-29
**No code.** A detailed read-through of the schedule before writing anything
against it, which surfaced one correctness bug and several places where the plan
was quietly optimistic.

### The bug: the migration would have blinded the working system

The rewrite's central promise is that the old code keeps running until the
session that deletes it. But the migration was scheduled to *execute* in week 3,
moving `inbox.md`, `boards/*.md` and `calendar/*.md` into `strips/` — while the
legacy shell, which reads those exact files via `Vault.list_tasks()` and
`AgendaFile`, remained the daily driver until the new surface landed in week 5.

**Two weeks with a system that compiles but cannot see your tasks.** That is a
broken state sitting exactly where the plan claimed there would never be one.

Fixed by splitting build from execution:

- **Week 3** builds the migration tool, tests it, and verifies the dry-run diff.
  Nothing moves.
- **Week 5** executes it as the first act of the week, immediately followed by
  S10/S11 — the surface that reads strips. The vulnerable window shrinks from two
  weeks to hours inside one session.

A stale consequence fixed at the same time: S16's note that kiosk boot could
launch the legacy entry point is wrong post-migration. It launches `python -m
bloc`; the cinematic boot sequence arrives with S12 in the same week.

Worth naming the pattern — this is the same class of defect as the `**due:**`
mismatch between `ui/autoflight.py:262` and `core/vault.py:77`: two parts of the
system drifting out of agreement about who reads what. It showed up in the
schedule before it could show up in the code.

### Month 1 violated the plan's own rule

The plan says, in bold, *never do two chore sessions in a row*. Month 1 as
written was eight consecutive infrastructure sessions with no visible payoff
until week 5 — the highest-probability abandonment point in the whole schedule,
at double the project's natural pace.

The fix was a swap, because one session was mis-placed: **S9 (HAL) has no
consumer until S12's boot probes in week 11**, so sitting in week 4 was pure
thematic tidiness. Meanwhile **D1 (the recorder) barely depends on the strip
model** — it needs audio capture, a `debriefs/` directory, and S8's `[debrief]`
config section.

So D1 moved to week 4 and S9 to week 6. Three things improved at once: month 1
now ends with something usable that evening; the corpus deadline — the only
deadline in the plan with zero slack — gained two weeks of shakedown, growing the
corpus from ~28 toward ~40; and S9 still lands five weeks before its first
consumer.

Because direct-to doesn't exist until week 5, D1 binds a temporary key in the
legacy shell and S11 rebinds it to direct-to, retiring the key. Strangler-fig
applied to a keybinding.

### Month 4 was overloaded — S15 is really two sessions

Porting a 966-LOC pygame application onto a new data model *and* deleting the
entire legacy tree was budgeted as one half-week session. Split into S15a (the
port — drawing code intact, data layer replaced) and S15b (deletion plus the
broken-import chase).

**S15a is scheduled into week 12**, alongside S13 and S14 — the two lightest
sessions in the plan — making that a deliberate three-session week. This is what
keeps every peripheral inside the four months rather than pushing e-ink out.
Month 4 now has no remaining slack, so the cut order is a live expectation rather
than an emergency brake.

### D2's mechanics needed pinning down

"Background transcription on a worker thread" hid three decisions that determine
whether the dead-zone corpus survives:

- **The WAV persists in `debriefs/pending/` until transcription *succeeds*.**
  `keep_audio = false` means discard-after-success, never never-write. Conflating
  those silently eats a debrief on any crash — during a month when nobody is
  watching.
- **The pending directory is a queue, drained on next boot.** Quitting
  mid-transcription then costs nothing. Designing it as a queue from day one also
  means P1 hardens it into a systemd job as a deployment change rather than a
  rewrite.
- **Whisper loads on the worker only.** Boot stays instant, but `small` at int8
  is roughly a gigabyte resident — fine on 8 GB, and the point where the resident
  model daemon stops being theoretical.

### Two frictions the plan had not named

**The corpus depends on a busy person's daily discipline.** Capture must be
trivial to reach or the dead zone yields 8 rambles rather than 40. Resolved by
routing it through direct-to — one key, then the word `debrief` — rather than
adding a fifth global key. The global set stays closed at four (direct-to, back,
home, quit); new capabilities cost a keyword, not a keybinding. That property is
what keeps the surface small as the system grows. Target is *most days*, not a
streak.

**D3's eval corpus cannot enter the repo.** Real rambles are a diary, and this
repository may be shown in a university application. The eval harness runs
locally against `~/bloc/debriefs/` and reports aggregate precision/recall;
committed tests use synthetic fixtures only. Same principle as the vault: real
data stays home, only the machinery is public.

### Smaller corrections

- **Trend honesty at n≈40:** present observations, not statistics — sparklines
  and "you said *tired* 9 times; 6 were Thursdays", never correlation
  coefficients. Defensible statistics need months of data; that is a backlog
  item.
- **Migration safety had a gap:** moving originals to `archive/pre-unification/`
  protects against loss but not against a buggy migrator mangling content while
  writing. A plain `tar` of `~/bloc` to a different location is now a required
  pre-flight step.
- **WSL is a hard rule from S2 onward,** not a suggestion. All three fatal Linux
  bugs came from Windows-only development, and weeks 1–10 are laptop weeks. Any
  session touching `keys.py` or an input loop verifies under WSL.
- **Pace, stated in hours:** two sessions a week is roughly 5–6 focused hours
  weekly for three of the four months.

### Next

**S2** — `bloc/ui/`, as planned.
