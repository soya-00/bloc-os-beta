"""
Presentation primitives — the layer that owns the BLOC aesthetic.

Planned modules:

    theme.py    HUD / VOID / FOG glyph sets and colour maps
    vocab.py    aviation status vocabulary (LOGGED, SCRUBBED, FAULT, ...)
    keys.py     the single cross-platform key reader
    widgets.py  leader(), bar(), sparkline(), panel(), separator()
    screen.py   base screen loop

Every glyph and status word in the system resolves here, so selecting the FOG
theme genuinely removes all symbols.
"""
