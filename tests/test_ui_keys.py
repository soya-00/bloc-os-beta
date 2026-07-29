"""
Key decoding.

The escape decoder takes its reader as an argument specifically so the sequence
mapping can be tested without a terminal — which is the part that was broken on
Linux in v0.1 and never exercised anywhere.
"""

import pytest

from bloc.ui.keys import Key, decode_escape, translate


def reader(chars):
    """A `read_more` that yields `chars` in turn, then None (nothing available)."""
    it = iter(chars)

    def read_more():
        return next(it, None)

    return read_more


class TestDecodeEscape:
    @pytest.mark.parametrize(
        ("sequence", "expected"),
        [
            ("[A", Key.UP),
            ("[B", Key.DOWN),
            ("[C", Key.RIGHT),
            ("[D", Key.LEFT),
            ("[H", Key.HOME),
            ("[F", Key.END),
            ("OA", Key.UP),
            ("OD", Key.LEFT),
        ],
    )
    def test_arrow_and_navigation_sequences(self, sequence, expected):
        assert decode_escape(reader(sequence)) == expected

    @pytest.mark.parametrize(
        ("sequence", "expected"),
        [("[3~", Key.DELETE), ("[1~", Key.HOME), ("[4~", Key.END)],
    )
    def test_numeric_sequences(self, sequence, expected):
        assert decode_escape(reader(sequence)) == expected

    def test_bare_escape_when_nothing_follows(self):
        """Escape must not hang waiting for a sequence that is not coming."""
        assert decode_escape(reader("")) == Key.ESC

    def test_unrecognised_introducer_is_escape(self):
        assert decode_escape(reader("Z")) == Key.ESC

    def test_truncated_sequence_is_escape(self):
        assert decode_escape(reader("[")) == Key.ESC

    def test_unknown_final_byte_is_escape(self):
        assert decode_escape(reader("[Q")) == Key.ESC

    def test_unterminated_numeric_sequence_does_not_hang(self):
        assert decode_escape(reader("[99")) == Key.ESC


class TestTranslate:
    @pytest.mark.parametrize(
        ("char", "expected"),
        [
            ("\r", Key.ENTER),
            ("\n", Key.ENTER),
            ("\t", Key.TAB),
            ("\x7f", Key.BACKSPACE),
            ("\x08", Key.BACKSPACE),
        ],
    )
    def test_control_characters(self, char, expected):
        assert translate(char) == expected

    @pytest.mark.parametrize("char", ["a", "Z", "1", "·", " "])
    def test_printable_characters_pass_through(self, char):
        assert translate(char) == char


def test_key_constants_cannot_collide_with_printable_input():
    """Key names are bracketed so they can never equal a typed character."""
    names = [v for k, v in vars(Key).items() if not k.startswith("_")]
    assert all(n.startswith("<") and n.endswith(">") for n in names)
    assert len(set(names)) == len(names)


def test_raw_mode_is_reentrant_and_safe_without_a_tty():
    """Tests run without a terminal; nesting must still be a no-op, not an error."""
    from bloc.ui.keys import raw_mode

    with raw_mode(), raw_mode():
        pass
