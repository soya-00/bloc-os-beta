"""
The injectable now.

`today()` deserving its own test looks like overkill until you notice that
`now().date()` is the *UTC* date, and is therefore wrong for several hours every
day in most of the world — including the UK in summer.
"""

import time
from datetime import UTC, datetime, timedelta

import pytest

from bloc.core import clock


def test_now_is_aware_and_utc():
    assert clock.now().tzinfo is not None
    assert clock.now().utcoffset() == timedelta(0)


def test_local_now_is_aware():
    assert clock.local_now().tzinfo is not None


def test_local_wallclock_is_naive():
    assert clock.local_wallclock().tzinfo is None


class TestFrozen:
    def test_pins_now(self):
        instant = datetime(2026, 8, 14, 9, 12, 3, tzinfo=UTC)
        with clock.frozen(instant):
            assert clock.now() == instant
            assert clock.now() == instant

    def test_restores_afterwards(self):
        before = clock.now()
        with clock.frozen(datetime(2000, 1, 1, tzinfo=UTC)):
            pass
        assert clock.now() >= before

    def test_nests(self):
        outer = datetime(2026, 1, 1, tzinfo=UTC)
        inner = datetime(2027, 1, 1, tzinfo=UTC)
        with clock.frozen(outer):
            with clock.frozen(inner):
                assert clock.now() == inner
            assert clock.now() == outer

    def test_restores_even_when_the_block_raises(self):
        with pytest.raises(RuntimeError), clock.frozen(datetime(2000, 1, 1, tzinfo=UTC)):
            raise RuntimeError
        assert clock.now().year > 2000

    def test_rejects_a_naive_instant(self):
        with pytest.raises(ValueError, match="aware"):
            with clock.frozen(datetime(2026, 8, 14, 9, 0)):
                pass


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="POSIX only")
class TestLocalVsUtc:
    """
    The reason `today()` is not `now().date()`.

    At 23:30 in Sydney it is still the previous day in UTC, so a due date
    computed from the UTC date lands a day early.
    """

    def test_today_follows_the_local_zone(self, monkeypatch):
        instant = datetime(2026, 8, 14, 22, 30, tzinfo=UTC)

        monkeypatch.setenv("TZ", "UTC")
        time.tzset()
        with clock.frozen(instant):
            assert clock.today().day == 14

        monkeypatch.setenv("TZ", "Australia/Sydney")
        time.tzset()
        with clock.frozen(instant):
            assert clock.today().day == 15

        monkeypatch.delenv("TZ")
        time.tzset()

    def test_wallclock_follows_the_local_zone(self, monkeypatch):
        instant = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)

        monkeypatch.setenv("TZ", "UTC")
        time.tzset()
        with clock.frozen(instant):
            assert clock.local_wallclock().hour == 12

        monkeypatch.setenv("TZ", "Europe/London")
        time.tzset()
        with clock.frozen(instant):
            assert clock.local_wallclock().hour == 13  # BST

        monkeypatch.delenv("TZ")
        time.tzset()
