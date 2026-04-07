import os
import sys
import shutil
import time
from datetime import datetime
from pathlib import Path


# ─── USB DETECTION ────────────────────────────────────────
# Looks for a mounted drive containing a BLOC marker file.
# On Windows: scans removable drive letters
# On Linux/Pi: scans /media and /mnt

BLOC_MARKER   = "BLOC_VAULT"     # file we look for/create on USB root
SYNC_FOLDER   = "bloc_backup"    # folder name on the USB drive


def _find_usb_windows() -> Path | None:
    """Scan drive letters for a removable drive with BLOC marker."""
    import string
    import ctypes

    REMOVABLE = 2   # DRIVE_REMOVABLE constant

    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:\\")
        try:
            dtype = ctypes.windll.kernel32.GetDriveTypeW(str(drive))
            if dtype == REMOVABLE and drive.exists():
                # Accept any removable drive — create marker if not present
                return drive
        except Exception:
            continue
    return None


def _find_usb_linux() -> Path | None:
    """Scan /media and /mnt for any mounted USB volume."""
    search_roots = [Path("/media"), Path("/mnt")]
    for root in search_roots:
        if not root.exists():
            continue
        # /media/username/DRIVE_NAME
        for candidate in root.rglob("*"):
            if candidate.is_dir() and candidate.stat().st_dev != root.stat().st_dev:
                return candidate
    return None


def find_usb() -> Path | None:
    """Return the root path of an inserted USB drive, or None."""
    if os.name == 'nt':
        return _find_usb_windows()
    else:
        return _find_usb_linux()


# ─── SYNC LOGIC ───────────────────────────────────────────

def sync_to_usb(vault_root: Path, usb_root: Path) -> dict:
    """
    Copy the entire vault to USB drive.
    Returns a result dict with counts and status.
    """
    dest = usb_root / SYNC_FOLDER

    # Write marker file so we recognise this drive next time
    marker = usb_root / BLOC_MARKER
    if not marker.exists():
        marker.write_text(
            f"BLOC VAULT BACKUP\nInitialised: "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        )

    # Timestamp subfolder — keeps a rolling history
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_dir = dest / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    copied  = 0
    skipped = 0
    errors  = []

    # Walk the vault, mirror structure
    for src_file in vault_root.rglob("*"):
        if src_file.is_dir():
            continue

        # Skip config — don't back up sensitive settings
        if "config" in src_file.parts:
            skipped += 1
            continue

        relative = src_file.relative_to(vault_root)
        dst_file = backup_dir / relative
        dst_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(src_file, dst_file)
            copied += 1
        except Exception as e:
            errors.append(str(src_file.name))

    # Write a manifest
    manifest = backup_dir / "MANIFEST.txt"
    manifest.write_text(
        f"BLOC VAULT BACKUP\n"
        f"Timestamp : {timestamp}\n"
        f"Files     : {copied}\n"
        f"Skipped   : {skipped}\n"
        f"Errors    : {len(errors)}\n"
    )

    # Prune old backups — keep last 5
    _prune_old_backups(dest, keep=5)

    return {
        "copied":    copied,
        "skipped":   skipped,
        "errors":    errors,
        "dest":      str(backup_dir),
        "timestamp": timestamp,
    }


def _prune_old_backups(dest: Path, keep: int = 5):
    """Delete oldest backup folders beyond the keep limit."""
    if not dest.exists():
        return
    backups = sorted(
        [d for d in dest.iterdir() if d.is_dir()],
        key=lambda d: d.name
    )
    for old in backups[:-keep]:
        shutil.rmtree(old, ignore_errors=True)


# ─── SYNC UI ──────────────────────────────────────────────

class SyncUI:
    """
    USB vault sync screen.
    Detects USB, shows status, confirms before writing.
    """

    def __init__(self, vault, env):
        self.vault = vault
        self.env   = env

    def run(self):
        self.env.clear()
        self.env.accent("    ◈ BLOC OS  ◀  VAULT SYNC\n")
        self.env.separator("double")
        print()

        # ── detect USB ────────────────────────────────────
        self.env.dim("    ◈ SCANNING FOR USB ···· STAND BY")
        usb = find_usb()

        if not usb:
            print()
            self.env.alert(
                "    ◈ NO CONTACT ··········· NO USB DRIVE DETECTED\n"
            )
            self.env.dim("    Insert a USB drive and try again.")
            self._pause()
            return

        print()
        self.env.accent(f"    ◈ DRIVE ACQUIRED ······· {usb}")
        self.env.dim(
            f"    ◈ DESTINATION ·········· "
            f"{usb / SYNC_FOLDER}"
        )

        # ── show what will be synced ───────────────────────
        stats = self.vault.stats()
        print()
        self.env.dim(f"    ◈ NOTES ················ {stats['notes']:02d} files")
        self.env.dim(f"    ◈ TASKS ················ {stats['tasks']:02d} active")
        self.env.dim(
            f"    ◈ JOURNAL ·············· "
            f"{stats['journal_entries']:02d} entries"
        )
        print()

        # ── confirm ───────────────────────────────────────
        self.env.separator()
        self.env.alert(
            "    ◈ CAUTION ············· THIS WILL WRITE TO USB\n"
        )
        self.env.accent("    ◈ CONFIRM SYNC ········· [y/n] : ", end="")

        try:
            confirm = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = 'n'

        if confirm != 'y':
            print()
            self.env.dim("    ◈ SYNC ················· ABORTED")
            self._pause()
            return

        # ── run sync ──────────────────────────────────────
        print()
        self.env.dim("    ◈ WRITING TO USB ······· STAND BY")
        time.sleep(0.3)

        result = sync_to_usb(self.vault.root, usb)

        print()
        if result["errors"]:
            self.env.alert(
                f"    ◈ SYNC COMPLETE ········ "
                f"{result['copied']} files  ·  "
                f"{len(result['errors'])} FAULTS"
            )
            for e in result["errors"][:5]:
                self.env.dim(f"         FAULT · {e}")
        else:
            self.env.accent(
                f"    ◈ SYNC COMPLETE ········ "
                f"{result['copied']} files  ·  ALL CONFIRMED"
            )

        self.env.dim(
            f"    ◈ BACKUP LOGGED ········ "
            f"{result['timestamp']}"
        )
        self._pause()

    def _pause(self):
        print()
        self.env.dim("    ◈ STANDING BY ·········· PRESS ANY KEY")
        if os.name == 'nt':
            import msvcrt
            msvcrt.getwch()
        else:
            import tty, termios
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)