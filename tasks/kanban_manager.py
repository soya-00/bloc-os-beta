from pathlib import Path
from tasks.kanban import KanbanBoard


class KanbanManager:
    """Manages multiple kanban boards stored in ~/bloc/tasks/boards/"""

    def __init__(self, boards_dir: Path):
        self.boards_dir = boards_dir
        self.boards_dir.mkdir(parents=True, exist_ok=True)

    def list_boards(self) -> list:
        """Return list of dicts with board info."""
        boards = []
        for f in sorted(self.boards_dir.glob("*.md")):
            board = KanbanBoard(f)
            boards.append({
                "name": board.title,
                "path": f,
                "cards": board.card_count(),
                "columns": len(board.columns),
            })
        return boards

    def new_board(self, name: str) -> KanbanBoard:
        """Create a new board."""
        slug = name.lower().replace(" ", "-")
        filepath = self.boards_dir / f"{slug}.md"
        board = KanbanBoard(filepath)
        board.title = name
        board.save()
        print(f"✅ Board created: {name}")
        return board

    def open_board(self, index: int) -> KanbanBoard:
        """Open a board by index (0-based)."""
        boards = self.list_boards()
        if 0 <= index < len(boards):
            return KanbanBoard(boards[index]["path"])
        return None