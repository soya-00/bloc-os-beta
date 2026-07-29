"""
The MFD contract.

Most of these tests exist to hold one property: *no key means two different
things in two places*. That was the actual complaint about v0.1 — `f`, `s`, `k`,
`n` and `a` each meant one thing at the top level and something else inside a
screen, with nothing on screen to tell you which. So the interesting assertions
here are the ones about collisions and about globals surviving a hostile screen,
not the ones about layout.
"""

import io

import pytest

from bloc.ui.console import Console
from bloc.ui.keys import Key
from bloc.ui.screen import (
    GLOBAL_KEYS,
    GLOBALS,
    PANEL,
    ScreenStack,
    Signal,
    SoftKey,
    key_name,
    prompt,
    render_header,
    render_legend,
)
from bloc.ui.theme import FOG, HUD, THEMES


class Fake:
    """A screen. Note it subclasses nothing — that is the contract under test."""

    def __init__(self, title="TEST", soft=(), on_key=None, status=None):
        self.title = title
        self._soft = soft
        self._on_key = on_key
        self._status = status
        self.drawn = 0
        self.seen = []

    def render(self, console):
        self.drawn += 1
        console.write(f"body of {self.title}")

    def soft_keys(self):
        return self._soft

    def on_key(self, key):
        self.seen.append(key)
        return self._on_key(key) if self._on_key else None

    def status(self):
        return self._status


def stack(*, screen=None, keys=(), direct_to=None):
    """A stack wired to a scripted key sequence and a captured stream."""
    stream = io.StringIO()
    it = iter(keys)
    st = ScreenStack(
        console=Console(HUD, stream),
        direct_to=direct_to,
        read_key=lambda: next(it, "q"),
    )
    st._stack = [screen or Fake()]
    return st, stream


# ── the closed global set ─────────────────────────────────


class TestGlobalKeys:
    def test_there_are_exactly_four(self):
        """
        The set is closed by decision, not by accident. A fifth global is the old
        collision problem with extra steps, so this test is here to make growing
        the set a conscious edit rather than a drive-by addition.
        """
        assert len(GLOBALS) == 4
        assert {label for _, label in GLOBALS} == {"DIRECT-TO", "BACK", "HOME", "QUIT"}

    def test_every_advertised_global_is_actually_bound(self):
        for key, _ in GLOBALS:
            assert key in GLOBAL_KEYS

    def test_home_has_a_synonym_for_keyboards_without_the_key(self):
        assert GLOBAL_KEYS["`"] is GLOBAL_KEYS[Key.HOME] is Signal.HOME

    def test_only_one_letter_is_reserved(self):
        """Every other letter stays available to screens forever."""
        assert {k for k in GLOBAL_KEYS if k.isalpha()} == {"q"}


class TestSoftKeyValidation:
    @pytest.mark.parametrize("key", sorted(GLOBAL_KEYS))
    def test_a_soft_key_cannot_claim_a_global(self, key):
        with pytest.raises(ValueError, match="global key"):
            SoftKey(key, "SOMETHING")

    def test_the_error_names_the_conflict(self):
        with pytest.raises(ValueError, match="QUIT"):
            SoftKey("q", "QUEUE")

    def test_empty_key_rejected(self):
        with pytest.raises(ValueError, match="needs a key"):
            SoftKey("", "NOTHING")

    def test_ordinary_keys_are_fine(self):
        assert SoftKey("c", "COMPLETE").key == "c"

    def test_two_soft_keys_on_one_screen_may_not_collide(self):
        screen = Fake(soft=(SoftKey("c", "COMPLETE"), SoftKey("c", "CLEAR")))
        st, _ = stack(screen=screen)
        with pytest.raises(ValueError, match="binds 'c' to both"):
            st.dispatch("c")


# ── legend ────────────────────────────────────────────────


class TestLegend:
    def test_globals_render_even_with_no_soft_keys(self):
        text = "\n".join(render_legend())
        for _, label in GLOBALS:
            assert label in text

    def test_a_screen_cannot_suppress_the_globals(self):
        """A screen that could hide BACK could strand you on it."""
        text = "\n".join(render_legend([SoftKey("c", "COMPLETE")]))
        assert "BACK" in text and "HOME" in text

    def test_soft_keys_come_before_globals(self):
        lines = render_legend([SoftKey("c", "COMPLETE")])
        assert "COMPLETE" in lines[0]
        assert "DIRECT-TO" in lines[-1]

    def test_disabled_key_keeps_its_slot(self):
        """Panel buttons do not move when they grey out."""
        on = render_legend([SoftKey("c", "COMPLETE")])[0]
        off = render_legend([SoftKey("c", "COMPLETE", enabled=False)])[0]
        assert len(on) == len(off)
        assert "[C]" in on
        assert "[C]" not in off
        assert "COMPLETE" in off

    def test_no_line_exceeds_the_panel(self):
        many = [SoftKey(c, f"ACTION{c.upper()}") for c in "abcdefgxyz"]
        assert all(len(line) <= PANEL for line in render_legend(many))

    def test_a_cell_is_never_split_across_lines(self):
        many = [SoftKey(c, f"ACTION{c.upper()}") for c in "abcdefgxyz"]
        text = "\n".join(render_legend(many))
        for c in "abcdefgxyz":
            assert f"[{c.upper()}] ACTION{c.upper()}" in text

    def test_one_overlong_cell_still_gets_a_line(self):
        [line] = render_legend([SoftKey("z", "Z" * 200)])[:1]
        assert "Z" * 200 in line


@pytest.mark.parametrize(
    ("key", "expected"),
    [("c", "C"), ("+", "+"), (Key.ESC, "ESC"), (Key.UP, "UP"), (" ", "SPC")],
)
def test_key_name(key, expected):
    assert key_name(key) == expected


class TestHeader:
    def test_title_ends_at_the_panel_column(self):
        assert len(render_header("objectives", HUD.glyphs)) == PANEL

    def test_title_is_upper_cased(self):
        assert "OBJECTIVES" in render_header("objectives", HUD.glyphs)

    @pytest.mark.parametrize("theme", THEMES.values(), ids=lambda t: t.name)
    def test_header_uses_theme_glyphs(self, theme):
        out = render_header("agenda", theme.glyphs)
        assert len(out) == PANEL
        assert not out.startswith(" ")

    def test_fog_header_carries_no_symbols(self):
        """FOG has an empty corner glyph; it must not leave a ragged indent."""
        assert render_header("agenda", FOG.glyphs).startswith("BLOC OS")


# ── dispatch ──────────────────────────────────────────────


class TestDispatch:
    def test_soft_key_handler_is_invoked(self):
        fired = []
        screen = Fake(soft=(SoftKey("c", "COMPLETE", lambda: fired.append(1)),))
        st, _ = stack(screen=screen)
        st.dispatch("c")
        assert fired == [1]

    def test_disabled_soft_key_does_nothing(self):
        fired = []
        screen = Fake(soft=(SoftKey("c", "C", lambda: fired.append(1), enabled=False),))
        st, _ = stack(screen=screen)
        assert st.dispatch("c") is True
        assert fired == []

    def test_unclaimed_key_falls_through_to_the_screen(self):
        screen = Fake()
        st, _ = stack(screen=screen)
        st.dispatch(Key.DOWN)
        assert screen.seen == [Key.DOWN]

    def test_a_screen_without_on_key_ignores_unknown_keys(self):
        class Bare:
            title = "BARE"

            def render(self, console):
                pass

        st, _ = stack(screen=Bare())
        assert st.dispatch("z") is True

    def test_quit_stops_the_loop(self):
        st, _ = stack()
        assert st.dispatch("q") is False

    def test_globals_beat_a_screen_that_tries_to_swallow_them(self):
        """
        The ordering guarantee: globals resolve before the screen is consulted,
        so an over-eager `on_key` cannot trap you.
        """
        greedy = Fake(on_key=lambda key: Signal.STAY)
        st, _ = stack(screen=greedy)
        assert st.dispatch("q") is False
        assert greedy.seen == []


class TestNavigation:
    def test_returning_a_screen_pushes_it(self):
        child = Fake("CHILD")
        screen = Fake(soft=(SoftKey("e", "EDIT", lambda: child),))
        st, _ = stack(screen=screen)
        st.dispatch("e")
        assert st.depth == 2
        assert st.current is child

    def test_back_pops_one_level(self):
        st, _ = stack()
        st.push(Fake("CHILD"))
        st.dispatch(Key.ESC)
        assert st.depth == 1

    def test_back_at_the_root_is_a_no_op_not_an_exit(self):
        """On an appliance there is nothing below home to fall into."""
        st, _ = stack()
        assert st.dispatch(Key.ESC) is True
        assert st.depth == 1

    def test_home_collapses_the_whole_stack(self):
        st, _ = stack()
        st.push(Fake("A"))
        st.push(Fake("B"))
        st.dispatch("`")
        assert st.depth == 1

    def test_stay_and_none_both_hold_position(self):
        for outcome in (None, Signal.STAY):
            st, _ = stack(screen=Fake(soft=(SoftKey("c", "C", lambda o=outcome: o),)))
            st.dispatch("c")
            assert st.depth == 1


# ── direct-to ─────────────────────────────────────────────


class TestDirectTo:
    def test_typed_line_reaches_the_callback(self):
        seen = []
        st, _ = stack(keys=["c", "a", "l", "l", Key.ENTER], direct_to=seen.append)
        st.dispatch("/")
        assert seen == ["call"]

    def test_escape_cancels_without_calling_back(self):
        seen = []
        st, _ = stack(keys=["x", Key.ESC], direct_to=seen.append)
        st.dispatch("/")
        assert seen == []

    def test_blank_entry_is_not_dispatched(self):
        seen = []
        st, _ = stack(keys=[Key.ENTER], direct_to=seen.append)
        st.dispatch("/")
        assert seen == []

    def test_direct_to_works_with_no_callback_wired(self):
        """S3 ships before the parser exists; the key must still be harmless."""
        st, _ = stack(keys=["h", "i", Key.ENTER])
        assert st.dispatch("/") is True

    def test_the_callback_can_navigate(self):
        child = Fake("CHILD")
        st, _ = stack(keys=["g", "o", Key.ENTER], direct_to=lambda text: child)
        st.dispatch("/")
        assert st.current is child

    def test_reachable_from_every_screen_in_the_stack(self):
        seen = []
        st, _ = stack(keys=["a", Key.ENTER], direct_to=seen.append)
        st.push(Fake("DEEP"))
        st.push(Fake("DEEPER"))
        st.dispatch("/")
        assert seen == ["a"]


class TestPrompt:
    def read(self, keys):
        stream = io.StringIO()
        it = iter(keys)
        return prompt(Console(HUD, stream), read_key=lambda: next(it)), stream

    def test_collects_printable_characters(self):
        text, _ = self.read(["n", "o", "t", "e", Key.ENTER])
        assert text == "note"

    def test_backspace_deletes(self):
        text, _ = self.read(["c", "a", "t", Key.BACKSPACE, "b", Key.ENTER])
        assert text == "cab"

    def test_backspace_on_empty_buffer_is_harmless(self):
        text, _ = self.read([Key.BACKSPACE, Key.BACKSPACE, "x", Key.ENTER])
        assert text == "x"

    def test_escape_returns_none(self):
        text, _ = self.read(["x", Key.ESC])
        assert text is None

    def test_whitespace_only_reads_as_cancelled(self):
        text, _ = self.read([" ", " ", Key.ENTER])
        assert text is None

    def test_navigation_keys_do_not_leak_into_the_text(self):
        """`get_key` returns bracketed names like `<up>`; none may be typed."""
        text, _ = self.read(["a", Key.UP, Key.DOWN, Key.TAB, "b", Key.ENTER])
        assert text == "ab"

    def test_the_label_is_shown(self):
        _, stream = self.read(["x", Key.ENTER])
        assert "DIRECT-TO >" in stream.getvalue()


# ── the frame ─────────────────────────────────────────────


class TestDraw:
    def test_every_screen_gets_a_legend(self):
        """S3's acceptance test: the legend is the framework's, not the app's."""
        st, stream = stack(screen=Fake("AGENDA"))
        st.draw()
        out = stream.getvalue()
        assert "AGENDA" in out
        assert "body of AGENDA" in out
        for _, label in GLOBALS:
            assert label in out

    def test_status_is_shown_when_offered(self):
        st, stream = stack(screen=Fake(status="3 OVERDUE"))
        st.draw()
        assert "3 OVERDUE" in stream.getvalue()

    def test_a_screen_without_status_still_draws(self):
        class Bare:
            title = "BARE"

            def render(self, console):
                console.write("x")

        st, stream = stack(screen=Bare())
        st.draw()
        assert "BARE" in stream.getvalue()


class TestRun:
    def test_draws_then_reads_until_quit(self):
        screen = Fake()
        st, _ = stack(screen=screen, keys=[Key.DOWN, Key.DOWN, "q"])
        st.run(screen)
        assert screen.drawn == 3
        assert screen.seen == [Key.DOWN, Key.DOWN]

    def test_ctrl_c_exits_cleanly(self):
        def boom():
            raise KeyboardInterrupt

        st, _ = stack()
        st.read_key = boom
        st.run(Fake())  # must not propagate

    def test_run_resets_the_stack(self):
        st, _ = stack(keys=["q"])
        st.push(Fake("STALE"))
        home = Fake("HOME")
        st.run(home)
        assert st.depth == 1
        assert st.current is home
