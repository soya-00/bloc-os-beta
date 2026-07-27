"""
Applications — one file per screen.

Apps are declared as data in `registry.py` (a table of dotted factory paths),
not discovered by import side effects. A decorator would require importing every
app module at boot to register it, which re-imports pygame and reloads Whisper —
exactly the eager-loading cost the registry exists to remove. A table is lazy by
construction and inspectable at runtime, which the boot checklist needs.

Contract, deliberately thin:

    run()       required. Blocks; returns when the user quits the screen.
    status()    optional. Must be non-blocking — it runs after every keystroke.

No base class and no ABC: duck typing plus getattr keeps the migration cost of
an existing app at zero.
"""
