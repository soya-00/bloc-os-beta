import os
from datetime import datetime
from pathlib import Path


class Vault:
    """
    Core vault manager for BLOC.
    Handles all file operations within the bloc directory.
    Produces no output — all UI feedback is handled by the shell.
    """

    def __init__(self):
        self.root = Path.home() / "bloc"
        self.dirs = {
            "notes":    self.root / "notes",
            "journal":  self.root / "journal",
            "tasks":    self.root / "tasks",
            "boards":   self.root / "tasks" / "boards",
            "calendar": self.root / "calendar",
            "archive":  self.root / "archive",
            "exports":  self.root / "exports",
            "config":   self.root / "config",
            "sessions": self.root / "sessions",
        }
        self._ensure_structure()

    def _ensure_structure(self):
        for path in self.dirs.values():
            path.mkdir(parents=True, exist_ok=True)

    # ─── CREATE ───────────────────────────────────────────

    def new_note(self, title: str, content: str = "", tags: list = []) -> Path:
        """Create a new note and return its path."""
        date     = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H-%M")
        slug     = title.lower().replace(" ", "-")[:40]
        filename = f"{date}-{time_str}-{slug}.md"
        filepath = self.dirs["notes"] / filename

        tag_str = " ".join(f"#{t}" for t in tags) if tags else ""
        body    = f"# {title}\n\n{tag_str}\n\n{content}"

        filepath.write_text(body, encoding="utf-8")
        return filepath

    def new_journal(self, content: str = "") -> Path:
        """Create or append to today's journal entry."""
        date     = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date}.md"
        filepath = self.dirs["journal"] / filename
        time_str = datetime.now().strftime("%H:%M")

        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8")
            filepath.write_text(
                existing + f"\n\n---\n*{time_str}*\n\n{content}",
                encoding="utf-8"
            )
        else:
            filepath.write_text(
                f"# Journal — {date}\n\n*{time_str}*\n\n{content}",
                encoding="utf-8"
            )
        return filepath

    def new_task(self, title: str, due: str = "", tags: list = []) -> None:
        """Append a task to inbox.md"""
        filepath = self.dirs["tasks"] / "inbox.md"

        if not filepath.exists():
            filepath.write_text("# Inbox\n\n", encoding="utf-8")

        tag_str   = " ".join(f"#{t}" for t in tags)
        due_str   = f" {due}" if due else ""
        task_line = f"- [ ] {title}{due_str} {tag_str}\n"

        with open(filepath, "a", encoding="utf-8") as f:
            f.write(task_line)

    # ─── READ ─────────────────────────────────────────────

    def list_notes(self) -> list:
        """Return all notes sorted by modified date."""
        notes = list(self.dirs["notes"].glob("*.md"))
        notes.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return notes

    def list_tasks(self) -> list:
        """Return all incomplete tasks from inbox.md"""
        filepath = self.dirs["tasks"] / "inbox.md"
        if not filepath.exists():
            return []

        tasks = []
        for line in filepath.read_text(encoding="utf-8").splitlines():
            if line.startswith("- [ ]"):
                tasks.append(line[6:].strip())
        return tasks

    def read_file(self, filepath: Path) -> str:
        return filepath.read_text(encoding="utf-8")

    def search(self, query: str) -> list:
        """Search all .md files for query string. Returns list of (file, line)."""
        results = []
        for md_file in self.root.rglob("*.md"):
            if "archive" in str(md_file):
                continue
            for i, line in enumerate(
                md_file.read_text(encoding="utf-8").splitlines()
            ):
                if query.lower() in line.lower():
                    results.append((md_file, i + 1, line.strip()))
        return results

    # ─── UPDATE ───────────────────────────────────────────

    def complete_task(self, index: int) -> bool:
        """Mark a task as complete by index (1-based)."""
        filepath = self.dirs["tasks"] / "inbox.md"
        if not filepath.exists():
            return False

        lines      = filepath.read_text(encoding="utf-8").splitlines()
        task_count = 0
        for i, line in enumerate(lines):
            if line.startswith("- [ ]"):
                task_count += 1
                if task_count == index:
                    done_date = datetime.now().strftime("%Y-%m-%d")
                    lines[i]  = line.replace("- [ ]", "- [x]") + f"  {done_date}"
                    filepath.write_text("\n".join(lines), encoding="utf-8")
                    return True
        return False

    def delete_task(self, index: int) -> bool:
        """Delete a task by index (1-based)."""
        filepath = self.dirs["tasks"] / "inbox.md"
        if not filepath.exists():
            return False

        lines      = filepath.read_text(encoding="utf-8").splitlines()
        task_count = 0
        for i, line in enumerate(lines):
            if line.startswith("- [ ]"):
                task_count += 1
                if task_count == index:
                    lines.pop(i)
                    filepath.write_text("\n".join(lines), encoding="utf-8")
                    return True
        return False

    # ─── DELETE / ARCHIVE ─────────────────────────────────

    def archive_file(self, filepath: Path) -> Path:
        """Move a file to archive instead of deleting."""
        dest = self.dirs["archive"] / filepath.name
        filepath.rename(dest)
        return dest

    # ─── UTILS ────────────────────────────────────────────

    def stats(self) -> dict:
        """Return vault statistics."""
        notes   = list(self.dirs["notes"].glob("*.md"))
        tasks   = self.list_tasks()
        journal = list(self.dirs["journal"].glob("*.md"))
        return {
            "notes":           len(notes),
            "tasks":           len(tasks),
            "journal_entries": len(journal),
        }

    def list_files(self, folder: str = "notes") -> list:
        """
        List all .md files in a vault folder.
        Returns list of dicts with name, path, modified, words.
        """
        target = self.dirs.get(folder, self.dirs["notes"])
        files  = list(target.glob("*.md"))
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        result = []
        for f in files:
            content  = f.read_text(encoding="utf-8")
            words    = len(content.split())
            modified = datetime.fromtimestamp(
                f.stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M")
            result.append({
                "name":     f.name,
                "path":     f,
                "modified": modified,
                "words":    words,
            })
        return result