"""Smoke tests for the package skeleton."""

import subprocess
import sys

import bloc


def test_version_is_exposed():
    assert bloc.__version__


def test_subpackages_import():
    import bloc.apps  # noqa: F401
    import bloc.config  # noqa: F401
    import bloc.core  # noqa: F401
    import bloc.hal  # noqa: F401
    import bloc.jobs  # noqa: F401
    import bloc.services  # noqa: F401
    import bloc.services.voice  # noqa: F401
    import bloc.ui  # noqa: F401


def test_entry_point_exits_nonzero_until_boot_is_ported():
    result = subprocess.run(
        [sys.executable, "-m", "bloc"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "not wired up yet" in result.stderr
