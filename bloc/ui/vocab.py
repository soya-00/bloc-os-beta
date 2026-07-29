"""
Status vocabulary — every user-facing status word in the system.

The v0.1 rule, from the comment at `ui/shell.py:35`:

    All user-facing status language lives here.
    Never scatter raw "ERROR" / "OK" strings across UI code.

The rule was right; the enforcement was not. Three copies of this table existed
(`ui/shell.py:38`, `ui/kanban_ui.py:22`, `ui/pulse_ui.py:26`) and had already
drifted apart — not in their values, which agreed everywhere they overlapped,
but in coverage: each screen carried only the subset it happened to need, so
adding a status meant guessing which copies to update.

This is the union of all three. Values are unchanged from v0.1.
"""

from __future__ import annotations

from types import MappingProxyType

V: MappingProxyType[str, str] = MappingProxyType(
    {
        # ── outcomes ──────────────────────────────────────
        "saved": "LOGGED",
        "deleted": "SCRUBBED",
        "confirmed": "CONFIRMED",
        "complete": "TARGET NEUTRALIZED",
        "aborted": "ABORTED",
        "ended": "SESSION ENDED · LOG SAVED",
        # ── faults ────────────────────────────────────────
        "error": "FAULT",
        "warning": "CAUTION",
        "not_found": "NO CONTACT",
        "no_signal": "NO SIGNAL",
        # ── transient states ──────────────────────────────
        "loading": "ACQUIRING",
        "standby": "STANDING BY",
        "empty": "CLEAR",
    }
)


def status(key: str) -> str:
    """
    Look up a status word.

    Raises on an unknown key rather than returning a placeholder: a status
    string that silently renders as empty is how UI copy rots unnoticed.
    """
    try:
        return V[key]
    except KeyError:
        raise KeyError(f"unknown status {key!r}; known: {', '.join(sorted(V))}") from None
