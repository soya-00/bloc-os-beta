"""
Domain core — no terminal, no hardware, no network. Fully unit-testable.

    files.py    atomic writes, one sanitised slug, collision-safe paths
    clock.py    time helpers with an injectable "now"
    formats.py  one parser per vault file format, symmetric with its writer
    vault.py    filesystem CRUD; the single source of truth

Planned:

    strips.py   the unified record — task, card, agenda block and flight strip
    views.py    board / agenda / strip / list queries over the one store
    state.py    atomic JSON state under ~/bloc/state/
    index.py    rebuildable SQLite FTS cache over the vault
    events.py   in-process pub/sub

Two rules hold this layer together. **Markdown on disk stays canonical** —
anything else is a cache that can be deleted and rebuilt from it. And **a value
that can be written must parse back equal**, which is what `formats.py` exists to
guarantee: v0.1 persists eight date formats and uses not one of them
symmetrically.
"""
