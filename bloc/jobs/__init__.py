"""
One-shot jobs invoked by `systemd --user` timers on the appliance.

Each job reads the vault and state, does its work, and exits. Supervision,
restart and logging come from systemd rather than from a scheduler maintained
here — on a real system you declare units, you do not write a supervisor.

Planned jobs:

    sync.py           periodic vault backup
    agenda_alert.py   fires when a time block starts
    reindex.py        rebuild the SQLite FTS cache
"""
