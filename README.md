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

Version 0.2 is a rebuild in progress. The `bloc/` package is being grown
subsystem by subsystem while the legacy modules at the repository root keep
running — see [`docs/DECISIONS.md`](docs/DECISIONS.md) for the running log.

**`python main.py` is the working entry point until the boot sequence is
ported.**

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

## The vault

All data is plain Markdown and TOML on disk. Nothing is stored in a database,
and every file is readable and editable without BLOC.

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

## Development

```bash
ruff check .
pytest
```

## Licence

MIT
