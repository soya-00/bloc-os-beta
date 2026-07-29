# BLOC OS — Design System

How every screen is laid out and coloured, and why. This is the reference the UI
code is written against; when a screen and this document disagree, this document
is right and the screen is a bug.

Written after building three prototypes and comparing them, not before. Every
rule below has a render behind it that made the problem visible.

---

## 1. The frame

Every screen has the same four regions, in the same order, at the same sizes.
This is the single most important rule here — it is what makes the traffic scope
and the objectives list read as one program rather than two.

```
◈ BLOC   OBJECTIVES     LONDON   17:51:47Z   18 STRIPS   3 OVERDUE      ◉ VAULT
────────────────────────────────────────────────────────────────────────────────

  <body — the screen's own content, laid out on the grid>

────────────────────────────────────────────────────────────────────────────────
[C] COMPLETE  [E] EDIT  [+] NEW  [M] MOVE     [/] DIRECT-TO  [ESC] BACK  [Q] QUIT
```

**Status bar**, one line. Brand, then the screen name, then readouts left to
right, then a link/health indicator hard right. Never scrolls, never changes
height.

**Body.** The only region a screen controls.

**Soft-key row**, one line. The screen's own actions on the left, the four
globals on the right. Always visible, always in that order. A screen cannot
suppress the globals — a screen that could hide `BACK` could strand you on
itself.

The traffic scope obeys this identically, drawn in pixels rather than
characters. Same fields, same order, same hard-right health indicator.

---

## 2. The grid

**Four columns.** The scope's four strip bays are 480 px across a 1920 px panel;
terminal screens divide their width the same way. A strip in the objectives list
and the same strip on the scope therefore land on the same column.

```python
from bloc.ui.widgets import columns, span

cols = columns(console.width)      # four Column(start, width)
detail = span(cols, 0, 1)          # a panel under the first two bays
```

Sharing a grid is what makes the frame *structural*. A shared palette alone
gets you two screens that are the same colour and different shapes.

**Below 120 columns the grid collapses to one column.** Four columns of nine
characters is not a layout, it is a bug that renders. The 80-column SSH window
is a real case: the Pi is developed on remotely from week 11, and a layout that
only works at 1080p makes that miserable.

**Nothing is a fixed width.** v0.1 had `COL_WIDTH = 52` twice, `LAND_COL = 48`
and `STATUS_COL = 52`, which is exactly why alignment drifted between screens.
Width comes from `Console.width` and is passed down.

---

## 3. Colour

### Colour is a role

Every palette entry is named for what it *means*. There is no `amber` in the
codebase; there is `attention`. This is what lets one system have three real
implementations, and it stops a screen reaching for "the orange one" and
inventing a meaning nobody else knows about.

**Surfaces** — what a thing sits on.

| Role | Used for |
|---|---|
| `background` | the screen |
| `surface` | a strip cell, a panel |
| `surface_dead` | the same, for completed work |
| `rule` / `rule_dead` | dividers |

**Text hierarchy** — how loud a piece of text is. Strictly descending in
luminance: `primary` → `secondary` → `dim` → `faint`.

**State** — what something *is*. One mapping, every screen.

| Role | Meaning | On the scope |
|---|---|---|
| `active` | in progress | descending |
| `pressure` | overdue, pushing on you | climbing |
| `queued` | waiting | level |
| `attention` | needs a decision | conflict, alert |
| `critical` | failed, conflicting | — |
| `fixed` | infrastructure: titles, airports | airports, headings |

The three bands do not mix. Using a state colour for hierarchy — reaching for
`attention` because a heading should stand out — is how a palette rots.

### Never colour alone

Anything conveyed by colour is also conveyed by something else. An overdue strip
carries the `flag` glyph (`▌`) on its left edge as well as `pressure` colouring.

Colour alone fails in daylight on a glossy panel, fails on the VOID theme, fails
entirely on FOG, and fails permanently for red-green colour blindness. This one
is not negotiable.

### Legibility is tested, not asserted

`theme.py` exports `luminance()` and `contrast()` (WCAG), and the test suite
enforces floors against the surface each role sits on:

| Band | Floor | Why |
|---|---|---|
| `primary`, `secondary`, `fixed` | 7.0:1 | AAA — the text you read constantly |
| `dim` | 4.5:1 | AA body text — labels you actually read |
| `faint` | 3.0:1 | AA large/UI — recedes, but "recede" ≠ "unreadable" |
| state colours on `surface` | 4.5:1 | read at a glance inside a cell |

These are in `theme.py` rather than in the tests because a config file can
supply a palette, and an unreadable theme should be something the loader can
reject rather than something you discover on a sunlit panel.

> **Watch the measurement.** Relative luminance is weighted — the eye is roughly
> seven times more sensitive to green than to blue. HUD's `primary` `(0,255,65)`
> sums *lower* than `secondary` `(124,194,158)` but reads considerably brighter.
> An early version of the ramp test averaged the channels and declared a correct
> palette broken.

---

## 4. The three environments

Not three glyph sets — three genuine answers to "what can this display do".

| | HUD | VOID | FOG |
|---|---|---|---|
| Glyphs | aviation (`◈ ▶ ▢`) | brackets (`[ ] [x]`) | plain text |
| Colour | full hue | neutral brightness ramp | none |
| For | the device | mono panels, colour blindness | any terminal, SSH, pipes |

**FOG has every palette role set to `None`,** and the writer emits no escape at
all — not even a reset. That makes it the strongest available test that meaning
never lives in colour: if a screen is unusable in FOG, it is saying something in
colour that it never says in words.

**VOID separates state by brightness only** — every state colour is a neutral
grey. It is the theme to check when you suspect a screen has become
hue-dependent.

Colour depth is detected, not assumed: truecolor where available, the 256-colour
cube where not, nothing when piped or when `NO_COLOR` is set. The development
machine is a truecolor terminal; the Pi's own console is not, and a palette that
only works on the laptop is a palette that breaks on the device.

---

## 5. Strips

A strip is a task, a kanban card, an agenda block and a flight strip — one
record seen from different angles. **It renders identically everywhere.** If the
objectives list and the scope's bays draw a strip differently, the object model
is not unified, it is only shared storage.

```
▌ BLK-041   DENTIST              #health      2d
  callsign  title                tag          due
```

- **Left edge** — `flag` glyph in `attention` when it needs you, blank otherwise.
  Fixed width, so nothing shifts when the flag appears.
- **Callsign** — coloured by state. The only place state colour appears in a row.
- **Title** — `fixed`, truncated with `…` if it must be. Cells truncate visibly;
  `leader()` never truncates, because a ragged edge beats a silently shortened
  task title.
- **Due** — `attention` when overdue, `faint` otherwise.
- Completed strips use `surface_dead` and drop to `faint` throughout.

Bays are `INCOMING · ACTIVE · HOLDING · LANDED` — the strip statuses, one bay per
column.

### Fields drop; they never overlap

A four-column grid on a 150-column terminal gives each bay 34 characters, and
callsign + title + tag + due needs about 38. Something has to give, and the
order is fixed:

1. **Flag, callsign and due always render.** Whether it needs you, which strip
   it is, and when it is due.
2. **Title takes whatever is left**, truncated with `…`.
3. **Tag is dropped first** — when title and tag cannot both fit, the tag goes.

> Found by rendering, not by reasoning: an earlier pass stamped the tag at a
> fixed offset and produced `#2dalt` and `34mudy` where two fields had collided.
> An overlapping field is unreadable and silently wrong; a missing field is
> merely less informative. **Never let two fields share a cell.**

---

## 6. Type

One monospace family, and the terminal picks it. The pygame renderer resolves a
platform font (Menlo, DejaVu Sans Mono, Consolas) with a `match_font` fallback —
**never a hardcoded path**, which broke the first macOS run.

Sizes exist only in the pixel renderer: 13 px data, 15 px body, 17 px labels,
20 px brand. The terminal has one size, which is the terminal's.

`UPPERCASE` for labels, status fields and bay titles. Sentence case for content —
task titles are the user's words and are never transformed.

---

## 7. Rules of thumb

1. **If it is not in `theme.py`, it is a bug.** v0.1 retyped `#00FF41` inside
   `ui/autoflight.py`, which is why the scope and the shell drifted apart.
2. **The theme owns characters; the layout owns columns.** A width inside theme
   data means a rule that cannot match the panel it sits in.
3. **Ask what a colour means before choosing one.** If there is no answer, the
   thing does not need a colour.
4. **Check FOG before shipping a screen.** It takes one config change and
   catches every place meaning leaked into colour.
5. **Render it.** Every rule in this document came from looking at output. The
   flat-green problem, the 52-column problem and the luminance mistake were all
   invisible in the source and obvious on screen.
