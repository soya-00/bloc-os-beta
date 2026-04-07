import os
from tasks.kanban import KanbanBoard
from tasks.kanban_manager import KanbanManager
from ui.environment import Environment

if os.name == 'nt':
    import msvcrt
    def get_key():
        return msvcrt.getwch()
else:
    import tty, termios, sys
    def get_key():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


V = {
    "saved":     "LOGGED",
    "deleted":   "SCRUBBED",
    "error":     "FAULT",
    "warning":   "CAUTION",
    "aborted":   "ABORTED",
    "standby":   "STANDING BY",
    "empty":     "CLEAR",
    "confirmed": "CONFIRMED",
}


class KanbanUI:
    def __init__(self, manager: KanbanManager, env: Environment):
        self.manager = manager
        self.env = env

    def clear(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def _pause(self):
        print()
        self.env.dim(f"    ◈ {V['standby']} ·········· PRESS ANY KEY")
        get_key()

    # ─── BOARD PICKER ─────────────────────────────────────

    def show_board_picker(self):
        while True:
            self.clear()
            boards = self.manager.list_boards()
            c = self.env.char

            self.env.header("BLOC  ◀  FLOW", "MISSION BOARDS")
            print()

            if not boards:
                self.env.dim(f"    ◈ BOARDS ················ {V['empty']}\n")
            else:
                for i, b in enumerate(boards, 1):
                    self.env.accent(f"    {i}.  {b['name'].upper()}")
                    self.env.dim(
                        f"         {b['columns']} cols"
                        f"  ····  "
                        f"{b['cards']} cards"
                    )
                    print()

            self.env.separator()
            self.env.primary(f"    n  ·  new board")
            self.env.primary(f"    q  ·  back")
            print()
            self.env.separator("double")
            self.env.accent(f"    CMD {c('arrow_rt')} ", end="")

            key = get_key().lower()

            if key == 'q':
                return
            elif key == 'n':
                self.clear()
                self.env.header("BLOC  ◀  FLOW", "NEW BOARD")
                print()
                self.env.accent("    ◈ BOARD NAME ··········· ", end="")
                name = input().strip()
                if name:
                    board = self.manager.new_board(name)
                    self.show_board(board)
            elif key.isdigit():
                index = int(key) - 1
                board = self.manager.open_board(index)
                if board:
                    self.show_board(board)

    # ─── BOARD VIEW ───────────────────────────────────────

    def show_board(self, board: KanbanBoard):
        while True:
            self.clear()
            c = self.env.char

            self.env.header(f"FLOW  ◀  {board.title}", "BOARD VIEW")
            print()

            for col_name, cards in board.columns.items():
                incomplete  = [c2 for c2 in cards if not c2["done"]]
                done_count  = len([c2 for c2 in cards if c2["done"]])

                self.env.accent(
                    f"    ── {col_name.upper()} ({len(incomplete)}) "
                    + "─" * max(1, 26 - len(col_name))
                )

                if not incomplete:
                    self.env.dim(f"       {V['empty']}\n")
                else:
                    for i, card in enumerate(incomplete, 1):
                        due  = f"  {card['due']}" if card["due"] else ""
                        tags = (
                            "  " + " ".join(f"#{t}" for t in card["tags"])
                            if card["tags"] else ""
                        )
                        flag = " !" if card.get("priority") == "high" else ""
                        self.env.primary(
                            f"    {i}.  {card['title']}{flag}{due}{tags}"
                        )
                    if done_count:
                        self.env.dim(f"         + {done_count} done")
                    print()

            self.env.separator()
            self.env.primary("    a  ·  add card      m  ·  move card")
            self.env.primary("    d  ·  delete card   +  ·  add column")
            self.env.primary("    q  ·  back")
            print()
            self.env.separator("double")
            self.env.accent(f"    CMD {self.env.char('arrow_rt')} ", end="")

            key = get_key().lower()

            if key == 'q':
                return
            elif key == 'a':
                self._add_card(board)
            elif key == 'm':
                self._move_card(board)
            elif key == 'd':
                self._delete_card(board)
            elif key == '+':
                self._add_column(board)

    # ─── CARD ACTIONS ─────────────────────────────────────

    def _add_card(self, board: KanbanBoard):
        self.clear()
        col_names = board.column_names()
        self.env.header(f"FLOW  ◀  {board.title}", "ADD CARD")
        print()

        for i, name in enumerate(col_names, 1):
            self.env.primary(f"    {i}.  {name}")
        print()
        self.env.accent("    ◈ COLUMN (number) ······ ", end="")
        try:
            col_index = int(input().strip()) - 1
            col_name  = col_names[col_index]
        except (ValueError, IndexError):
            self.env.alert(f"    ◈ {V['error']} ················ INVALID COLUMN")
            self._pause()
            return

        self.env.accent("    ◈ TITLE ················ ", end="")
        title = input().strip()
        if not title:
            return

        self.env.dim("    ◈ DUE DATE ············· (yyyy-mm-dd or blank): ", end="")
        due = input().strip()

        self.env.dim("    ◈ TAGS ················· (space separated): ", end="")
        tags_raw = input().strip()
        tags = tags_raw.split() if tags_raw else []

        self.env.dim("    ◈ HIGH PRIORITY ········ [y/n]: ", end="")
        priority = "high" if input().strip().lower() == 'y' else ""

        board.add_card(col_name, title, due=due, tags=tags, priority=priority)
        self.env.accent(
            f"\n    ◈ CARD ·················· {V['saved']} → {col_name.upper()}"
        )
        self._pause()

    def _move_card(self, board: KanbanBoard):
        self.clear()
        col_names = board.column_names()
        self.env.header(f"FLOW  ◀  {board.title}", "MOVE CARD")
        print()

        for i, name in enumerate(col_names, 1):
            cards = [c for c in board.columns[name] if not c["done"]]
            self.env.primary(f"    {i}.  {name} ({len(cards)})")
        print()

        self.env.accent("    ◈ FROM COLUMN ·········· ", end="")
        try:
            from_index = int(input().strip()) - 1
            from_col   = col_names[from_index]
        except (ValueError, IndexError):
            return

        cards = [c for c in board.columns[from_col] if not c["done"]]
        if not cards:
            self.env.dim(f"    ◈ COLUMN ··············· {V['empty']}")
            self._pause()
            return

        print()
        self.env.dim(f"    ◈ CARDS IN {from_col.upper()}")
        for i, card in enumerate(cards, 1):
            self.env.primary(f"    {i}.  {card['title']}")
        print()

        self.env.accent("    ◈ CARD NUMBER ·········· ", end="")
        try:
            card_index = int(input().strip()) - 1
        except ValueError:
            return

        print()
        self.env.dim("    ◈ MOVE TO:")
        for i, name in enumerate(col_names, 1):
            self.env.primary(f"    {i}.  {name}")
        print()

        self.env.accent("    ◈ TO COLUMN ············ ", end="")
        try:
            to_index = int(input().strip()) - 1
            to_col   = col_names[to_index]
        except (ValueError, IndexError):
            return

        full_cards   = board.columns[from_col]
        actual_index = 0
        count        = 0
        for j, c in enumerate(full_cards):
            if not c["done"]:
                if count == card_index:
                    actual_index = j
                    break
                count += 1

        success = board.move_card(from_col, actual_index, to_col)
        if success:
            self.env.accent(
                f"\n    ◈ CARD ·················· {V['confirmed']} → {to_col.upper()}"
            )
        else:
            self.env.alert(f"    ◈ {V['error']} ················ MOVE FAILED")
        self._pause()

    def _delete_card(self, board: KanbanBoard):
        self.clear()
        col_names = board.column_names()
        self.env.header(f"FLOW  ◀  {board.title}", "DELETE CARD")
        print()

        for i, name in enumerate(col_names, 1):
            cards = [c for c in board.columns[name] if not c["done"]]
            self.env.primary(f"    {i}.  {name} ({len(cards)})")
        print()

        self.env.accent("    ◈ FROM COLUMN ·········· ", end="")
        try:
            col_index = int(input().strip()) - 1
            col_name  = col_names[col_index]
        except (ValueError, IndexError):
            return

        cards = board.columns[col_name]
        if not cards:
            self.env.dim(f"    ◈ COLUMN ··············· {V['empty']}")
            self._pause()
            return

        for i, card in enumerate(cards, 1):
            self.env.primary(f"    {i}.  {card['title']}")
        print()

        self.env.accent("    ◈ DELETE CARD ·········· ", end="")
        try:
            card_index = int(input().strip()) - 1
            self.env.alert(
                f"    ◈ {V['warning']} ············· CONFIRM DELETION [y/n] : ",
                end=""
            )
            if input().strip().lower() == 'y':
                board.delete_card(col_name, card_index)
                self.env.accent(f"\n    ◈ CARD ·················· {V['deleted']}")
            else:
                self.env.dim(f"    ◈ DELETION ············· {V['aborted']}")
        except ValueError:
            pass
        self._pause()

    def _add_column(self, board: KanbanBoard):
        self.clear()
        self.env.header(f"FLOW  ◀  {board.title}", "ADD COLUMN")
        print()
        self.env.accent("    ◈ COLUMN NAME ·········· ", end="")
        name = input().strip()
        if name:
            board.add_column(name)
            self.env.accent(
                f"\n    ◈ COLUMN ··············· {V['saved']} · {name.upper()}"
            )
        self._pause()