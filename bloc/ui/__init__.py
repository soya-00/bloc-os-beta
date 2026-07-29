"""
Presentation primitives — the layer that owns the BLOC aesthetic.

    theme.py    HUD / VOID / FOG glyph sets and colour maps  (data only)
    vocab.py    aviation status vocabulary (LOGGED, SCRUBBED, FAULT, ...)
    keys.py     the single cross-platform key reader
    widgets.py  leader(), bar(), sparkline(), separator()    (pure functions)
    console.py  the only module that writes to a stream
    screen.py   the MFD contract — one key loop, soft keys as data

Two rules hold the layer together. **Every glyph and status word resolves here**,
so selecting the FOG theme genuinely removes all symbols — v0.1 hardcoded `◈` in
128 places and FOG rendered aviation glyphs regardless. And **widths belong to
layout, not to theme data**: `leader()` and `separator()` take their characters
from the theme and their column from the caller, which is why the header, the
rules and the soft-key legend can all end at the same column without the theme
knowing what that column is.
"""
