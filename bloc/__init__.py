"""
BLOC OS — aviation-instrument inspired operating environment.

Layering (each layer may import only from those below it):

    apps/       one file per screen; registered as data in apps/registry.py
    services/   long-lived domain logic: adsb, pulse, agenda, sync, voice
    hal/        hardware abstraction — display, audio, printer, controls, power
    core/       state, vault, formats, events, clock
    ui/         theme, vocabulary, key input, widgets
    config/     schema, validation, migration

The rule that keeps the aesthetic intact: no module outside `ui/` may contain a
raw glyph, colour code, or status word. Everything goes through `ui.theme` and
`ui.vocab`.
"""

__version__ = "0.2.0.dev0"
