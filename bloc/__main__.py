"""
Entry point for the rebuilt system — `python -m bloc` / `bloc`.

The rebuild is a strangler-fig migration: this package grows subsystem by
subsystem while the legacy modules at the repository root keep running. Until
the boot sequence is ported, `main.py` remains the working entry point.
"""

import sys


def main() -> int:
    sys.stderr.write(
        "BLOC OS: the rebuilt entry point is not wired up yet.\n"
        "Run `python main.py` until the boot sequence is ported.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
