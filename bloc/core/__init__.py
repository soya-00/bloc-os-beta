"""
Domain core — no terminal, no hardware, no network. Fully unit-testable.

Planned modules:

    state.py    atomic JSON state under ~/bloc/state/
    vault.py    filesystem CRUD; the single source of truth
    formats.py  one parser per vault file format, with round-trip tests
    index.py    rebuildable SQLite FTS cache over the vault
    events.py   in-process pub/sub
    clock.py    time helpers with an injectable "now"
"""
