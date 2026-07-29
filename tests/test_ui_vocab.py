"""Status vocabulary — the merge of v0.1's three divergent copies."""

import pytest

from bloc.ui.vocab import V, status


def test_covers_every_key_from_all_three_v01_copies():
    """
    Union of `ui/shell.py:38`, `ui/kanban_ui.py:22` and `ui/pulse_ui.py:26`.
    Each screen carried only the subset it happened to need.
    """
    expected = {
        "saved", "deleted", "confirmed", "complete", "aborted", "ended",
        "error", "warning", "not_found", "no_signal",
        "loading", "standby", "empty",
    }
    assert set(V) == expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("saved", "LOGGED"),
        ("deleted", "SCRUBBED"),
        ("error", "FAULT"),
        ("warning", "CAUTION"),
        ("complete", "TARGET NEUTRALIZED"),
        ("standby", "STANDING BY"),
        ("empty", "CLEAR"),
    ],
)
def test_values_match_v01(key, expected):
    """Wording is part of the aesthetic; the merge must not have edited it."""
    assert V[key] == expected


def test_no_raw_status_words_leak_through():
    """The whole point of the table: no bare OK/ERROR reaches the user."""
    assert not {"OK", "ERROR", "FAILED", "SUCCESS"} & set(V.values())


def test_unknown_key_raises_with_a_useful_message():
    with pytest.raises(KeyError, match="unknown status"):
        status("nope")


def test_table_is_immutable():
    with pytest.raises(TypeError):
        V["saved"] = "changed"
