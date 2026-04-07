import re
from pathlib import Path
from datetime import datetime


class KanbanBoard:
    """
    A single kanban board backed by a .md file.
    
    Column format in file:
    ## Column Name
    - [ ] Card title  📅 2026-03-05  #tag
    """

    DEFAULT_COLUMNS = ["Inbox", "In Progress", "Review", "Done"]

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.title = filepath.stem.replace("-", " ").title()
        self.columns = {}  # ordered dict: col_name → [cards]
        self.load()

    # ─── FILE I/O ─────────────────────────────────────────

    def load(self):
        """Parse .md file into columns and cards."""
        self.columns = {}

        if not self.filepath.exists():
            # New board — create default columns
            for col in self.DEFAULT_COLUMNS:
                self.columns[col] = []
            self.save()
            return

        current_col = None
        for line in self.filepath.read_text(encoding="utf-8").splitlines():
            # Column header
            if line.startswith("## "):
                current_col = line[3:].strip()
                self.columns[current_col] = []
            # Card (incomplete)
            elif line.startswith("- [ ]") and current_col:
                card = self._parse_card(line[6:].strip(), done=False)
                self.columns[current_col].append(card)
            # Card (complete)
            elif line.startswith("- [x]") and current_col:
                card = self._parse_card(line[6:].strip(), done=True)
                self.columns[current_col].append(card)

    def save(self):
        """Write current state back to .md file."""
        lines = [f"# {self.title}\n"]
        for col_name, cards in self.columns.items():
            lines.append(f"\n## {col_name}")
            if not cards:
                lines.append("")
            for card in cards:
                checkbox = "- [x]" if card["done"] else "- [ ]"
                due = f"  📅 {card['due']}" if card.get("due") else ""
                tags = "  " + " ".join(f"#{t}" for t in card["tags"]) if card.get("tags") else ""
                priority = "  🔥" if card.get("priority") == "high" else ""
                lines.append(f"{checkbox} {card['title']}{due}{tags}{priority}")

        self.filepath.write_text("\n".join(lines), encoding="utf-8")

    # ─── CARD PARSING ─────────────────────────────────────

    def _parse_card(self, text: str, done: bool) -> dict:
        """Parse a card line into a dict."""
        card = {
            "title": text,
            "done": done,
            "due": "",
            "tags": [],
            "priority": "",
            "notes": "",
        }

        # Extract due date
        due_match = re.search(r"📅\s+(\d{4}-\d{2}-\d{2})", text)
        if due_match:
            card["due"] = due_match.group(1)
            card["title"] = card["title"].replace(due_match.group(0), "").strip()

        # Extract tags
        tags = re.findall(r"#(\w+)", card["title"])
        card["tags"] = tags
        card["title"] = re.sub(r"#\w+", "", card["title"]).strip()

        # Extract priority
        if "🔥" in card["title"]:
            card["priority"] = "high"
            card["title"] = card["title"].replace("🔥", "").strip()

        return card

    # ─── OPERATIONS ───────────────────────────────────────

    def add_card(self, column: str, title: str, due: str = "", tags: list = [], priority: str = "") -> bool:
        """Add a card to a column."""
        if column not in self.columns:
            return False
        card = {
            "title": title,
            "done": False,
            "due": due,
            "tags": tags,
            "priority": priority,
            "notes": "",
        }
        self.columns[column].append(card)
        self.save()
        return True

    def move_card(self, from_col: str, card_index: int, to_col: str) -> bool:
        """Move a card from one column to another (0-based index)."""
        if from_col not in self.columns or to_col not in self.columns:
            return False
        cards = self.columns[from_col]
        if card_index < 0 or card_index >= len(cards):
            return False
        card = cards.pop(card_index)
        # Auto mark done if moving to Done column
        if to_col.lower() == "done":
            card["done"] = True
        self.columns[to_col].append(card)
        self.save()
        return True

    def delete_card(self, column: str, card_index: int) -> bool:
        """Delete a card by index (0-based)."""
        if column not in self.columns:
            return False
        cards = self.columns[column]
        if card_index < 0 or card_index >= len(cards):
            return False
        cards.pop(card_index)
        self.save()
        return True

    def add_column(self, name: str) -> bool:
        """Add a new column."""
        if name in self.columns:
            return False
        self.columns[name] = []
        self.save()
        return True

    def column_names(self) -> list:
        return list(self.columns.keys())

    def card_count(self) -> int:
        return sum(len(cards) for cards in self.columns.values())