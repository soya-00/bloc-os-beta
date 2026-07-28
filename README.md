# BLOC OS

An aviation-instrument inspired operating environment for productivity and time
management. Keyboard driven, no mouse, no windows — a boot sequence, an
instrument strip, and a set of single-key systems.

Notes, objectives and time blocks are plain Markdown in `~/bloc`. Live air
traffic is drawn on a radar scope, and your tasks are rendered as flight strips
over the London TMA.

```
    ◈ BLOC OS  v0.1
    ════════════════════════════════════════
    INITIALIZING SYSTEMS

    VAULT ········································ [ OK      ]
    CONFIG ······································· [ OK      ]
    AGENDA ······································· [ OK      ]
    TRAFFIC ······································ [ OK      ]
    VOICE ENGINE ································· [ OK      ]
    PRINTER ······································ [ STANDBY ]
```

## Status

**v0.2 is a rebuild in progress**, targeting a Raspberry Pi 5 appliance that
boots straight into BLOC. The `bloc/` package is being grown subsystem by
subsystem while the modules at the repository root keep running, so the tree is
never broken.

**`python main.py` is the working entry point** until the boot sequence is
ported.

Progress and the reasoning behind each step live in
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## Install

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python main.py
```

On the Raspberry Pi appliance, add the hardware extra:

```bash
pip install -e ".[dev,pi]"
```

## Commands

Current (v0.1) command set:

| Key | System |
|-----|--------|
| `v` | radio · voice input |
| `n` | new note |
| `t` | new objective |
| `l` | list objectives |
| `c` | mark objective complete |
| `d` | delete objective |
| `o` | open flight archive |
| `a` | agenda · day time blocks |
| `f` | traffic · autoflight ATC display |
| `k` | mission boards · kanban |
| `p` | pulse · focus timer |
| `x` | radar · london tma |
| `s` | settings |
| `q` | touchdown · shut down |

In v0.2 these collapse into four modes with contextual soft keys — see
*Where this is going* below.

## The vault

All data is plain Markdown and TOML on disk. Nothing is stored in a proprietary
format, and every file is readable and editable without BLOC.

```
~/bloc/
├── notes/                  YYYY-MM-DD-HH-MM-slug.md
├── journal/                YYYY-MM-DD.md
├── tasks/inbox.md          - [ ] objective  due  #tag
├── tasks/boards/*.md       kanban boards, one file per board
├── calendar/YYYY-MM-DD.md  ## 09:00 → 10:30 | DEEP WORK
├── sessions/YYYY-MM-DD.md  focus session logs
├── archive/  exports/
└── config/bloc.config      TOML
```

## Themes

Three display environments, selectable in settings:

- **HUD** — aviation glyphs, green phosphor
- **VOID** — bracket geometry, monochrome
- **FOG** — plain text, no symbols

## Where this is going

Four decisions shape v0.2. Each is argued in full in `docs/DECISIONS.md`.

**A multi-function display, not a menu.** Real avionics don't solve navigation
with long command lists — they use an MFD: a home *status* page, a few modes, and
soft keys along the bottom whose labels change with context. v0.2 replaces the 14
top-level commands with four modes — OBJECTIVES · AGENDA · TRAFFIC · SYSTEMS —
plus a global natural-language input available from any screen, typed or spoken.

**One record: the flight strip.** In ATC, a strip carries a callsign, times and a
status, and moves between bays as the flight progresses — which is simultaneously
a kanban card, an agenda block and a task. v0.2 unifies them into one record in
`~/bloc/strips/`, with boards, the agenda, flight strips and the objectives list
becoming four views of the same data rather than four separate stores.

**DEBRIEF.** Record a 30-second-to-2-minute ramble about your day. BLOC
transcribes it, proposes actionable to-dos for you to accept or reject, and
tracks recurring emotional and productivity signals over time — correlating what
you *said* with what you actually completed. Everything runs locally; recordings
never leave the device.

**A device, not an app.** A Raspberry Pi 5 in an instrument-panel enclosure:
kiosk boot with no login prompt, physical toggle switches and a rotary encoder, a
thermal printer for the daily agenda, and an e-ink standby display. A hardware
abstraction layer keeps the same code running on a laptop with none of it
attached.

## Development

```bash
ruff check .
pytest
```

Linting currently excludes the v0.1 modules at the repository root; each is
brought under the linter by the session that replaces it.

## Licence

MIT
