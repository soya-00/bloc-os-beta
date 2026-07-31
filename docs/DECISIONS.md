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

---

## S2 — The aesthetic layer

**Date:** 2026-07-29
**Milestone:** Month 1, week 1

### What changed

`bloc/ui/` now holds the canonical presentation layer: `theme.py` (glyph and
colour data), `vocab.py` (status words), `keys.py` (the single key reader),
`widgets.py` (pure layout functions) and `console.py` (the only module that
writes). 88 tests, all fast, none needing a terminal.

Nothing is wired into the running app yet. v0.1's own copies stay in place until
the sessions that port each screen — strangler fig, so the daily driver is
untouched.

### The three Linux bugs, and their shared root cause

All three came from the same mistake: toggling terminal mode around *every
individual keypress*.

- `ui/settings_ui.py:18` called `termios.tcgetattr(fd, termios.TCSADRAIN, old)`
  where it meant `tcsetattr`. Wrong arity, so every keypress raised `TypeError`
  and left the terminal raw.
- `ui/pulse_ui.py:15` and `ui/ambient_ui.py:15` called `select()` while stdin was
  still in *cooked* mode — raw mode was entered only after `select` reported
  readable. Cooked stdin is not readable until Enter, so the live countdown and
  the screensaver's exit-on-keypress never fired.

Fixed structurally rather than one at a time: `raw_mode()` is a context manager
held for the lifetime of a screen, and the read functions assume it is active.
It is re-entrant, so nesting is a no-op and a standalone `get_key()` can safely
enter it itself. There is now exactly one place in the system where terminal
mode is manipulated, so this class of bug has one place left to occur.

Related choices:

- **Cbreak, not full raw.** ISIG stays enabled so Ctrl-C still interrupts. v0.1
  used `setraw`, which on a locked-up screen leaves no way out.
- **Terminal flags set explicitly** (clear `ICANON`/`ECHO`, `VMIN=1`, `VTIME=0`)
  rather than via `tty.setcbreak`, whose handling of `ECHO` has differed across
  Python versions.
- **`raw_mode()` is a no-op when stdin is not a tty**, so tests and pipes work
  without special-casing.

### Choices made

- **Five modules, not the four planned.** Splitting `theme.py` (data) from
  `console.py` (I/O) earned its extra file: it is what lets every layout
  function be pure and directly testable, rather than asserting against captured
  stdout. v0.1's `Environment` conflated the two.

- **`Glyphs` is a frozen dataclass, not a dict.** v0.1's `env.char("bulet")`
  returned `""` silently. A mistyped field now fails at import.

- **The escape decoder takes its reader as an argument.** Arrow keys arrive as
  multi-byte sequences and decoding them is the fiddliest logic here, so it is a
  pure function over an injected `read_more` and tested without a terminal —
  including the case that matters most: a bare Escape must not hang waiting for
  a sequence that is not coming.

- **`vocab.py` is the union of v0.1's three copies.** Worth recording that they
  had *not* diverged in their values — every overlapping key agreed. They
  diverged in *coverage*: each screen carried only the subset it needed, so
  adding a status meant guessing which copies to update. Unknown keys now raise
  instead of returning a placeholder.

- **`bar()` clamps its fraction.** An overrunning focus timer yields a fraction
  above 1.0, and v0.1's unclamped `round(value * width)` would emit a bar wider
  than its own field and break the surrounding layout.

- **`sparkline(0, 0)` reads empty, not full.** `ui/shell.py:117` passed the same
  value as both `done` and `total`, so the header bar showed 100% regardless of
  what was outstanding. The caller was wrong, but the function can no longer be
  read as agreeing with it.

### A bug introduced and caught in the same session

The first version of `leader()` defaulted its fill character to `·`. Rendering
all three themes side by side showed FOG — documented as "no symbols" — still
drawing leaders out of middle dots.

That is precisely the v0.1 bug this layer exists to fix, relocated from 128 call
sites into one function signature. `leader_fill` is now **theme data** and
`leader()` takes a `Glyphs`; there is no default to fall back on.

The lesson worth keeping: *a hardcoded glyph anywhere below `theme.py` is the
bug, however few places it appears in.* Rendering every theme and looking at the
output caught what the unit tests did not, because the tests asserted on HUD.

### Not done, deliberately

- **The ruff `extend-exclude` list is unchanged.** `ui/` still holds eight v0.1
  modules; the entry comes off when the last of them goes in S15b.
- **Nothing is wired up.** `theme.py` supersedes `ui/environment.py`, but the
  legacy shell keeps its own copy until each screen is ported.

### Housekeeping

The D2 entry above was orphaned when PR #1 merged at an earlier head than the
branch tip, so it never reached `main`. Recovered by cherry-pick onto this
branch. Worth watching for on future merges: confirm the merge commit's parent
is the branch tip, not just that the merge succeeded.

### Next

**S3** — `bloc/ui/screen.py`, the MFD contract: the framework owns the key loop,
apps declare soft keys as data, the legend renders itself, and the four global
keys (direct-to, back, home, quit) work from every screen.

---

## S3 — The MFD contract

`bloc/ui/screen.py`. The v0.1 complaint was never the *number* of commands — a
real instrument panel has plenty of buttons. It was that the same key meant
different things in different places (`f`, `s`, `k`, `n`, `a` all collided
between the top level and inner screens), with nothing on screen to tell you
which, and no reliable way back to a known place. Eight copy-pasted `while True:`
loops with eight private binding tables is what produced that.

### The framework owns the loop

`ScreenStack` is the only key loop in BLOC. A screen is anything with `title` and
`render()`; `soft_keys()`, `on_key()` and `status()` are optional and resolved
with `getattr`. No base class, no ABC — the same duck-typed contract chosen for
apps, for the same reason: a screen starts at ten lines and grows only where it
needs to.

Handlers return an `Outcome` — `None`/`STAY` to hold position, a `Signal` to
navigate, or a screen instance to push. That is the whole navigation vocabulary,
and it means no screen ever manipulates the stack directly.

### Why globals are dispatched before the screen sees the key

`dispatch()` resolves the four globals first, unconditionally, and only then
consults soft keys and `on_key`. The ordering is the guarantee: a screen cannot
swallow `BACK` even by accident, which is the failure mode that makes a nested UI
feel like a trap. There is a test that hands a deliberately greedy `on_key` a
`q` and asserts it never arrives.

Belt and braces on the same property: **`SoftKey` raises on construction if it
claims a global key.** "No key means two different things in two places" is
therefore a property of the type rather than a review checklist item, and
`ScreenStack` additionally rejects a screen that binds one key to two labels.

### Which four keys, and why mostly punctuation

    /     DIRECT-TO      Esc   BACK      `  HOME      q  QUIT

Reserving a *letter* globally steals it from every screen forever, so the globals
are punctuation with one deliberate exception: `q` is worth its letter because
every terminal user already expects it, and one letter out of twenty-six is a
cheap price. Everything else in the alphabet stays available to screens.

`Key.HOME` is accepted as a synonym for the backtick, but the legend advertises
the backtick — a Mac laptop has no Home key without a chord, and development is
happening on macOS until the Pi arrives in week 7.

**The set is closed.** There is a test asserting there are exactly four, so a
fifth global is a conscious edit rather than a drive-by addition. Every candidate
for a fifth — including DEBRIEF capture in D1 — goes through direct-to instead.

### Direct-to ships before its parser

`ScreenStack` takes `direct_to` as an injected callable. `IntentParser` does not
arrive until S10, so today the key opens the prompt, collects a line and drops
it. That is deliberate: the *key* is part of the interaction model and had to be
reserved now, whereas what it does with the text is S10's problem. The injection
seam is also what lets the entire loop be tested without a terminal.

`prompt()` is a hand-rolled line editor rather than `input()`, because the
terminal is in cbreak mode and `input()` would need canonical mode restored and
put back — v0.1's two attempts at exactly that are two of the three bugs that
made the Linux build unusable. Printable characters, backspace, enter, escape;
no history, no cursor movement. It is a command entry field on an instrument.

### A width was hiding in the theme data

Building the panel exposed that `Glyphs.separator` stored `"─" * 40` — a
pre-multiplied string, so every rule in the system was 40 columns while the
dot-leader column was 52. A rule that cannot match the panel it sits in is a
layout decision trapped in theme data.

The three separator fields are now **single characters**, and `separator()` takes
a width defaulting to `SEPARATOR_WIDTH`. Existing tests pass unchanged. This is
the same lesson as `leader_fill` in S2 arriving from the other direction: last
time a glyph was hardcoded outside the theme, this time a width was hardcoded
inside it. The rule that covers both: *the theme owns characters, the layout owns
columns.*

### Smaller decisions

- **A disabled soft key empties its bracket rather than vanishing** — `[ ] SCRUB`.
  Buttons on a real panel do not move when they grey out, and a legend that
  reflows on every state change is unreadable.
- **Back at the root is a no-op, not an exit.** On an appliance there is nothing
  below home to fall into. Quit is its own key.
- **`pythonpath = ["."]` added to the pytest config** so `pytest` works in a
  fresh clone without an editable install. A failing test should never actually
  be a missing `pip install -e .`.

### Verification

`ruff check` clean, 149 tests green. Rendered the panel in HUD and FOG side by
side: the FOG panel contains nothing but ASCII and ANSI colour codes — no
symbols, and the header, rules and legend all end at column 52.

### Next

**S4** — `bloc/core/`: `state.py` (atomic JSON), `vault.py` (filesystem CRUD as
the single source of truth) and `formats.py` (one parser per vault file format,
with round-trip tests). The `**due:**` mismatch between `ui/autoflight.py` and
`core/vault.py` exists precisely because three modules each hand-rolled their
own parser; `formats.py` is the fix, and its round-trip tests are what stop it
recurring. S4 and S5 are a pair — the strip record lands on top of these
parsers, and the plan's rule is never to stop between S5 and S6.

---

## H1 — Inbox data loss (hotfix, out of sequence)

`core/vault.py` writes task lines ending in `\n`, but `complete_task` and
`delete_task` rewrite the file with `"\n".join(lines)`, dropping it. The next
append lands on the previous line and **one task disappears from every reader**:

    after complete:  '- [x] Alpha …\n- [ ] Bravo '
    after next add:  '- [x] Alpha …\n- [ ] Bravo - [ ] Charlie \n'
    list_tasks()  →  ['Bravo - [ ] Charlie']

Also anchored the `- [ ]` → `- [x]` replace, which was unanchored and rewrote
the marker inside any title that contained it.

**This suspends S1's rule against patching modules scheduled for deletion**,
deliberately and once. The rule exists to stop effort going into doomed code,
not to let doomed code destroy the data the rewrite has to migrate. `inbox.md`
is one of the three files the week-5 migration reads, and every day this stayed
in cost another task and left another corrupted line to untangle. No test ships
with it — that is the other half of the rule holding: a test here would be
deleted with the module in S15b, and the replacement gets round-trip tests in S4.

---

## S4 — The core data layer

**Date:** 2026-07-29
**Milestone:** Month 1, week 2

### What changed

`bloc/core/` now holds `files.py` (atomic writes, one sanitised slug),
`clock.py` (injectable now), `formats.py` (one parser per format) and `vault.py`
(filesystem CRUD). 120 new tests, 269 total.

### What the survey found, and why it reshaped the session

A full read of every on-disk format v0.1 writes turned up more than the eleven
known defects:

- **Eighteen reader/writer disagreements across seven formats.** The `**due:**`
  mismatch was not an outlier, it was the pattern.
- **Not one of the eight persisted date formats is used symmetrically.** Every
  date written is re-read as an opaque string, by a regex matching markup no
  writer produces, or not at all. There is no `strptime` and no
  `date.fromisoformat` anywhere in v0.1.
- **Zero atomic writes** across fourteen write sites, six of which rewrite an
  entire file to change one record.
- **Two slug functions, neither sanitising** — `new_board("A/B")` resolves
  outside `boards/`.
- **Lossy kanban round-trips**: `#` anywhere in a card title is eaten, a literal
  `📅 2026-08-01` in a title is stolen as a due date.

That turned `formats.py` from tidying into the point of the session.

### Three kinds of time, and the thing that confirmed it

BLOC stores three things that look alike and behave differently:

| Kind | On disk | Question |
|---|---|---|
| instant | `2026-08-14T09:12:03Z` | when did this happen |
| date | `2026-08-14` | which day |
| wall clock | `2026-08-14T14:00` | what does the clock say |

Storing everything as UTC moves a 14:00 block to 13:00 across a DST change;
storing everything naive makes a running timer wrong across the same boundary.
Splitting them costs one rule and gets both right.

**TOML already made this distinction**, which is the part worth recording:
offset-date-time, local-date and local-date-time are exactly these three, and
`tomllib` returns aware `datetime`, `date` and naive `datetime` respectively.
Verified before writing tests against it. So strip frontmatter stores dates
natively rather than as strings and the type survives the round trip without
`formats.py` being involved at all — the functions there are for filenames,
legacy files and rendering.

### Choices made

- **`+++` frontmatter fences, not `---`.** The v0.1 journal format already uses
  `---` as its entry separator. A delimiter that collides with existing content
  is a parser that works until it doesn't, and there is a test with a journal
  separator inside a note body proving it.

- **`find_checkboxes` returns every task in a line, not the first.** H1 stopped
  new corruption but did not repair old, so the migration will meet
  `- [ ] Bravo - [ ] Charlie` lines. The cost is that a title genuinely
  containing `- [ ]` splits in two; the dry-run prints every split first.

- **Date disambiguation is explicit.** A `📅` date is unambiguously a due date. A
  bare date is not: `complete_task` appends a completion stamp after the tags,
  while a kanban card's bare date is a due date, and both appear on `[x]` lines.
  Rule: on a completed line the *last* bare date is the stamp and anything before
  it is the due date. That is exactly what each writer produces.

- **New notes get frontmatter; old ones are read leniently.** Title falls back to
  the first H1, tags to the header region, creation time to the filename stamp —
  the three things v0.1 wrote and never read back. **This is what makes it a
  change with no migration**: existing notes keep working untouched forever, and
  the week-5 migration stays scoped to tasks, boards and calendar.

- **Legacy tags are read from the first four lines only.** Scanning the whole
  document would harvest every `#word` in the prose, including comments in fenced
  code. v0.1 wrote the tag line third.

- **`format_wallclock` rejects an aware datetime** rather than dropping the
  offset quietly. The conversion is lossy, so it happens at the call site via
  `clock.local_wallclock()`, where it is visible.

- **`today()` is not `now().date()`.** That would be the *UTC* date, wrong for
  several hours a day in most of the world. There is a test that runs the same
  instant through two timezones and gets two different days.

- **`Vault.__init__` creates nothing.** `ensure()` is explicit, because
  constructing a vault to read one path should not scatter nine directories —
  which is how v0.1 left empty `exports/` folders in every test run. Legacy
  directories are addressable so the migration can find them, and never created.

- **`atomic_write_text` puts its temp file in the destination directory** and
  fsyncs the directory after the rename. `os.replace` is only atomic within one
  filesystem, and the directory fsync is the step people skip — it is the one
  that matters on a Pi with no UPS.

- **`BLOC_HOME` overrides the vault root**, so the migration can dry-run against
  a copy and tests need no `Path.home` monkeypatching.

### Two v0.1 search bugs fixed in passing

The archive exclusion was `if "archive" in str(path)` — a substring test against
the whole path, so any note whose own name contained the word was silently
invisible. Now a path-component test. And `read_text` was called unguarded, so
one non-UTF-8 file anywhere under the root aborted the entire search with a
traceback. Both have tests named after the symptom.

### Not done, deliberately

- **`state.py` moved to week 12.** Its first consumer is S13's pulse service,
  eight weeks out. Same call D2 made moving the HAL out of week 4, for the same
  reason: an interface with no caller gets the wrong shape. Nothing before week
  12 needs it — the app registry doesn't, DEBRIEF's pending queue is a directory
  of files rather than JSON, and S12's boot probes read live.
- **No task CRUD.** Tasks become strips in S5; porting `list_tasks`/`new_task`
  now means writing code deleted a week later.
- **No legacy format readers.** They live in S6's migration module and die with
  it, so throwaway code stays visibly throwaway.
- **Nothing deleted.** The legacy shell still reads `core/vault.py` for notes,
  journal and search, so the ruff exclude list is unchanged — same as S2 and S3.

### Verification

`ruff check` clean, 269 tests green. Against a scratch vault: a 14:00 block is
still 14:00 in November under `TZ=Europe/London`; a note titled
`../../etc/passwd #x 🔥` lands at `notes/2026-07-29-17-42-etc-passwd-x.md` with
its title intact; the same title twice in one minute gives two files;
`find_checkboxes` recovers both halves of a concatenated line; and a write torn
by a patched `os.replace` leaves the original byte-identical with no temp file
left behind.

### Next

**S5** — the strip record: schema, TOML frontmatter, parser, `bloc/core/strips.py`.
It lands directly on `formats.py`'s frontmatter and native TOML dates, so the
record type is mostly a dataclass and a validation pass. **S5 and S6 are a pair**
— the plan's rule is never to stop between them, because S6 builds the migration
that reads the legacy formats and a half-built migration is the one genuinely
dangerous state in this project.
## H2 — pygame-ce, and a supported-Python gap

`pip install -e .` fails on Python 3.14: upstream `pygame` has no 3.14 wheel, so
pip falls through to a source build and dies on clang. The manifest declares
`requires-python = ">=3.11"`, so this is a defect — it cannot install on a
Python it claims to support.

Switched to **`pygame-ce`**, the maintained community fork. It is a drop-in
providing the same `pygame` module, so no import changes anywhere, and it ships
wheels for new Python releases months ahead of upstream. The two conflict if
both are installed; a stale environment needs `pip uninstall pygame` first.

Worth recording the wider point, because it will recur: **the development
machine is ahead of the deployment target.** Raspberry Pi OS Bookworm ships
Python 3.11 and Trixie 3.13, while development is happening on 3.14. The
supported range is genuinely 3.11–3.14, not "whatever the laptop has", and a
dependency is only usable if it has wheels across that whole span. `ctranslate2`
(via `faster-whisper`) is the next most likely to fail the same way.

This also exposed the eager-import problem from the user's side rather than the
architecture's: a terminal application refused to start because a graphics
library would not compile. `ui/shell.py:15` imports `ui/autoflight.py`, which
imports pygame at module scope. S10's registry makes that a lazy dotted path,
and the verification for it — *"Whisper and pygame do not load unless invoked"* —
now has a concrete failure behind it rather than a principle.

---

## D6 — The design system

**Date:** 2026-07-29
**Milestone:** Month 1, week 2

### What changed

`docs/DESIGN.md` is new — the frame, the grid, the colour roles, the strip
anatomy. `bloc/ui/theme.py` is rewritten against it, `console.py` gains colour
depth detection, and `widgets.py` gains the grid. 331 tests.

### The renderer question, settled by rendering

Three prototypes of the traffic scope, then three of OBJECTIVES.

**Terminal graphics were proposed and rejected.** Half-blocks (200×112) cannot
draw a curve. Braille (200×224) fixes curves but renders too faint, and —
decisively — **braille glyph coverage and dot alignment vary by terminal font**,
so the map would look different in Terminal.app, on the Pi console and over SSH.
A screen whose appearance depends on which font a terminal ships is the exact
inconsistency the rework exists to remove. pygame-ce at 1920×1080 is clearly
better and took 260 lines.

**But pygame is not the answer for text screens.** Rendered OBJECTIVES twice at
full width — once in a terminal, once in pygame — and they are
near-indistinguishable. Pygame's advantage is *drawing*: curves, glow, arbitrary
geometry. A strip board has none of that. So:

- **Terminal** for OBJECTIVES · AGENDA · SYSTEMS · DEBRIEF
- **pygame-ce** for TRAFFIC only, over KMS/DRM on the Pi — no X, no desktop
- Both read `theme.py`. `ScreenStack.draw()` needs no second backend.

SSH access to every screen but the scope therefore costs nothing, which matters
from week 11 when the Pi is developed on remotely.

### The real cause of "inconsistent between screens"

Not the renderer. v0.1's scope carried **its own hardcoded palette, its own
status words and its own column constants** — `#00FF41` retyped inside
`ui/autoflight.py`, `LAND_COL = 48` beside `COL_WIDTH = 52`. Two screens cannot
drift if there is one place to change.

### Choices made

- **Colour is a role, never a colour.** `attention`, not `amber`. That is what
  lets VOID express the same system as a brightness ramp and FOG express it as
  nothing at all. Three bands — surface, text hierarchy, state — and mixing them
  is how a palette rots.

- **The four-column grid is shared with the scope.** Its strip bays are 480 px
  across 1920; terminal screens divide their width the same way, so a strip in
  the objectives list lands on the same column as the same strip on the scope.
  A shared palette gets two screens the same colour and different shapes; a
  shared grid makes the frame structural.

- **The grid collapses below 120 columns.** Four columns of nine characters is
  not a layout. An 80-column SSH window gets one column.

- **`COL = 52` is gone as a panel width.** Width comes from `Console.width`;
  `PANEL` is only a fallback for pipes and tests.

- **The three environments are three real answers**, not three glyph sets. HUD
  is the device. VOID separates state by *brightness only*, so it is legible
  with any colour blindness. **FOG sets every palette role to `None` and the
  writer emits no escape at all** — not even a reset. That makes FOG the
  strongest available test that meaning never lives in colour: a screen unusable
  in FOG is saying something in colour it never says in words.

- **Colour depth is detected, not assumed** — truecolor, then the 256-colour
  cube, then nothing when piped or when `NO_COLOR` is set. Development is on a
  truecolor terminal; the Pi's own console is not, and a palette that only works
  on the laptop breaks on the device.

- **Never colour alone.** An overdue strip carries the `flag` glyph on its left
  edge as well as `pressure` colouring. Fixed width, so nothing shifts when it
  appears.

### Two defects the renders exposed

**HUD's `primary` and `secondary` were the same green.** The hierarchy every
screen assumed did not exist on screen — most of "hard to read" was this one
line. Invisible in source, obvious the moment OBJECTIVES was rendered full-width
as a flat wall of one colour.

**Fields overlapped rather than dropping.** At 150 columns a bay is 34
characters and a strip needs 38, which produced `#2dalt` where tag and due had
collided. Now the drop order is fixed — flag, callsign and due always render,
title takes what is left, tag goes first. An overlapping field is silently
wrong; a missing one is merely less informative.

### A measurement mistake worth keeping

The first legibility test used `sum(rgb)` as brightness and declared the palette
broken: HUD's `primary` `(0,255,65)` sums *lower* than `secondary`
`(124,194,158)`. But relative luminance is weighted — the eye is roughly seven
times more sensitive to green than to blue — and by that measure the ramp was
already correct.

Fixing the test then exposed two colours that genuinely were too dark: `dim` at
3.9:1 and `faint` at 2.1:1 against the background. Both were brightened to meet
WCAG floors while keeping their hue.

`luminance()` and `contrast()` now live in `theme.py` rather than in the tests,
because S8 lets a config file supply a palette and an unreadable theme should be
something the loader can reject rather than something discovered on a sunlit
panel.

### Not done, deliberately

- **`bloc/ui/canvas.py` was never built** — the half-block/braille module this
  session's prototypes rejected.
- **No screens were ported.** S11 does that; D6 only lays the system down.
- **The pygame backend is not in the repository yet.** It arrives with S15a,
  built against `theme.py` rather than carrying its own colours.

### Next

**S5** — the strip record: schema, TOML frontmatter, parser, `bloc/core/strips.py`.
Lands on `formats.py`'s frontmatter and native TOML dates, so it is largely a
dataclass and a validation pass. **S5 and S6 are a pair** — never stop between
them, because a half-built migration is the one genuinely dangerous state in
this project.

---

## S5 — The strip record

**Date:** 2026-07-29
**Milestone:** Month 1, week 3

### What changed

`bloc/core/strips.py` — the one record that replaces tasks, kanban cards and
agenda blocks. 52 tests, 395 total.

v0.1 had three stores that could not talk: `t`/`l`/`c`/`d` operated on
`inbox.md`, `k` operated on `boards/*.md`, and there was no path between them —
so the ATC console, the best screen in the project, could not see board work at
all. The flight-strip metaphor was already right; this is the data model
catching up to it.

### Choices made

- **Five statuses, not four.** `queued · active · holding · done · scrubbed`.
  The original plan omitted `holding`, which left the HOLDING bay in the D6
  screens with nothing behind it. *Holding* means blocked on someone else —
  genuinely distinct from "not started yet", and the metaphor is exact: an
  aircraft in a hold is waiting for a clearance it has not been given.

- **`Status` is a `StrEnum`.** A typo fails at the boundary instead of
  propagating as a string nothing matches, and it still serialises to TOML as
  the plain word it looks like.

- **Status is not column.** `status` is the closed vocabulary the whole system
  understands; `column` is free-form board position invented by whoever made the
  board. A card in "Review" is still `active`. Conflating them is what would
  make boards and objectives disagree about the same strip.

- **The filename is the identity.** `next_id()` scans `strips/` and takes
  `max + 1`, so there is no counter file to corrupt, desync or contend on — the
  directory cannot disagree with itself about what exists. `create()` re-checks
  against the filesystem in a loop, so two creates in the same instant produce
  two strips rather than one overwriting the other.

- **Numbers are never reused.** A callsign is a permanent name for a thing that
  happened; reusing `BLK-041` would silently repoint every reference to it.

- **Dates are native TOML types.** `due` comes back a `date`, `created` an aware
  `datetime`, `scheduled_start` a naive one — the S4 discovery paying off, with
  `formats.py` not involved at all. The coercion helpers check the *kind* of
  time rather than parsing strings, because getting the kind wrong is the actual
  failure: a `scheduled_start` carrying an offset is an instant pretending to be
  a wall clock, and it drifts an hour twice a year without ever raising.

- **`with_status()` stamps the timestamp its transition implies.** Going active
  sets `started`; going done sets `completed`. In the caller, every caller would
  have to remember, and the one that forgets produces a completed strip with no
  completion time — which quietly breaks every trend DEBRIEF is meant to draw.

- **Strict parse, forgiving walk.** `Strip.parse()` raises rather than guessing;
  `StripStore.all()` catches, skips, and collects failures on `store.errors`.
  Guessing at the parse level would mean a corrupt strip silently becoming a
  *different valid* strip, which is worse than either — and swallowing at the
  walk level would mean a strip vanishing from your list, which is worse than an
  error.

- **Scrubbing sets a status; nothing is unlinked.** A delete you cannot undo is
  data loss with a friendly name, and `archive/` already exists for anything
  that genuinely has to leave.

- **Empty fields are omitted from the document.** The file is meant to be read
  and hand-edited; a wall of empty keys is neither.

### One thing the verification run caught

`all()` initially reported a stray `README.md` in `strips/` as a corrupt strip.
`next_id()` already ignored non-conforming filenames; `all()` did not, so a file
that never claimed to be a strip would have put a permanent error on the SYSTEMS
screen. Now both skip anything whose stem is not a callsign. Found by running the
plan's verification checklist rather than by a test — the test came after.

### Next

**S6** — the migration: `inbox.md` + `boards/*.md` + `calendar/*.md` → `strips/`.
Built and dry-run verified only; **execution waits for week 5**, hours before the
surface that reads the migrated data. **S5 and S6 are a pair and this is the
half-built state the plan warns about** — do not stop here.

---

## S6 — The migration

`bloc/jobs/legacy.py` and `bloc/jobs/migrate.py`. Reads `inbox.md`,
`boards/*.md` and `calendar/*.md`; writes strips. **Built and dry-run verified
only — execution waits for week 5**, hours before the surface that reads the
migrated data. Running it now would blind the legacy shell, which reads those
files directly, and break the strangler-fig promise that the old system works
until it is replaced.

453 tests.

### Most of the parsing already existed

S4 wrote `parse_checkbox()` against *both* v0.1 checkbox encodings — the bare
positional date in `inbox.md` and the `📅`/`#tag`/`🔥` form in `boards/*.md` —
including the rule that decides whether a bare date on a completed line is a due
date or a completion stamp. `find_checkboxes()` returns every task in a line
rather than the first, written specifically so this migration recovers both
halves of `- [ ] Bravo - [ ] Charlie`.

Neither needed rewriting. Only the agenda header wanted a parser of its own, and
it is one regex. An interface built for a caller that did not exist yet turned
out to fit — which is worth noting, because it is the opposite of what moving
`state.py` and the HAL to their consumers assumed.

### Plan, then apply

`plan()` returns everything it would do without touching disk; `apply()` is a
dumb executor over that result. The dry-run and the real run are therefore **the
same computation**, differing only in whether `apply` is called. A preview that
re-derives its own answer is a preview that can disagree with the thing it
previews.

Callsigns are allocated during planning, so the diff shows the real ids, and
`read_all()` has a deliberately fixed order — inbox, boards by name, calendar by
date — so two dry-runs agree and the real run assigns what the rehearsal showed.

### The order of operations

1. Dry run is the default; writing takes `--apply`. A flag survives in shell
   history, an interactive confirmation does not.
2. A vault already at the format version exits cleanly with nothing to do. This
   is what makes re-running a no-op, and it exits **0** so it is safe in a script.
3. A vault holding strips but carrying no version stamp is refused outright —
   that is a state this tool did not create, and guessing risks a second copy of
   every record.
4. **Strips are written before originals move.** A failure in the second half
   leaves the legacy vault intact and the old shell still working. There is a
   test that patches `shutil.move` to raise and asserts `inbox.md` is unchanged.
5. Originals are *moved* to `archive/pre-unification/`, keeping their relative
   layout, and an existing destination is never overwritten.
6. `.bloc-version` is stamped **last**. It is the commit point: the stamp means
   every earlier step finished.

None of that protects against this tool mangling content on the way through,
which is why the dry-run output ends by telling you to `tar` the vault
elsewhere first. The archive move guards against loss, not against a bug.

### Judgement calls

- **Board columns map to statuses**; unrecognised columns fall to `queued` and
  are flagged `(unmapped → queued)` in the diff rather than guessed at silently.
  `Review` maps to `active`, because status is not column — a card in review is
  still being worked on.
- **An unticked agenda block stays `queued` however old it is.** Marking elapsed
  blocks done would fabricate completion history in the record that is supposed
  to be the truth.
- **But a card sitting in a `Done` column is `done`, ticked or not.** These look
  contradictory and are not: the principle is **infer from a user's action,
  never from the passage of time.** Moving a card to Done is an action. Time
  passing is not.
- **Legacy completion dates widen to an instant at local noon.** `Strip.completed`
  is an instant and the old format stores only a date. Noon rather than midnight
  because midnight is the value most likely to cross a day boundary under a
  timezone conversion, and a stamp on the wrong day is worse than one that is
  vague about the hour.
- **Checkboxes nested in an agenda block stay in its body.** `Strip` has no
  parent field and inventing one inside a migration is scope nobody agreed to.
  The count is reported so the decision is visible rather than silent.

### Two things the verification run caught

Neither came from a test. Both tests were written afterwards.

**A `## ` line that did not parse as a block header was absorbed into the
previous block's body** — swallowing the broken header *and* everything beneath
it without a word. A heading is never body text; the check now runs before the
body branch and reports what it skipped.

**A block crossing midnight ended before it started.** `23:30 → 00:15` produced
an end 23 hours earlier than its start, because both times were dated from the
filename. v0.1 had the same flaw and got away with it by storing strings; in a
typed field it hands every view a negative duration. `end <= start` now rolls
the end to the next day.

That is three sessions running where working through the checklist by hand found
something reading the code did not.

### Deliberately not done

**Nothing is executed.** No vault is migrated, and `~/bloc` was never read — the
rehearsals ran against fixture vaults under `BLOC_HOME`.

**Nothing is deleted.** The legacy shell still reads all three formats, so the
ruff `extend-exclude` list is unchanged, as in S2 through S5.

**No parent/child link between strips**, no repair of titles that legacy formats
mangled (a `#` in a title was a tag in v0.1 and stays one), and no attempt to
merge duplicate records across the three sources.

### Next

**S7** — the view layer: board, agenda, flight-strip and list queries over the
one store. It is what makes the migrated data visible, and the first thing that
proves the unification is real rather than shared storage. Per the revised plan
it ends with a `--demo` flag, so the verification is executable rather than
described.
