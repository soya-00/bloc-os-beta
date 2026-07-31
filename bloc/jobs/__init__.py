"""
One-shot jobs invoked by `systemd --user` timers on the appliance.

Each job reads the vault and state, does its work, and exits. Supervision,
restart and logging come from systemd rather than from a scheduler maintained
here — on a real system you declare units, you do not write a supervisor.

    legacy.py     the three v0.1 vault formats, read one last time
    migrate.py    inbox.md + boards/*.md + calendar/*.md -> strips/

Planned jobs:

    sync.py           periodic vault backup
    agenda_alert.py   fires when a time block starts
    reindex.py        rebuild the SQLite FTS cache

`migrate` is the exception to the description above: it is run by hand, once,
and it is the only job here that can destroy data. Both it and `legacy` are
written to be deleted at S15b, once nothing reads the old formats.
"""
