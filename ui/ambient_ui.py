import os
import sys
import time
import math
import threading
from datetime import datetime
from core.radar import Radar, LONDON_TMA

if os.name == 'nt':
    import msvcrt
    def _kbhit(): return msvcrt.kbhit()
    def _getch(): return msvcrt.getwch()
else:
    import tty, termios, select
    def _kbhit():
        return select.select([sys.stdin], [], [], 0)[0] != []
    def _getch():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ─── LARGE ASCII CLOCK DIGITS ─────────────────────────────
# Each digit is 5 rows tall, 4 cols wide

DIGITS = {
    '0': ["┌──┐", "│  │", "│  │", "│  │", "└──┘"],
    '1': ["  ┐ ", "  │ ", "  │ ", "  │ ", "  ┘ "],
    '2': ["┌──┐", "   │", "┌──┘", "│   ", "└──┘"],
    '3': ["┌──┐", "   │", " ──┤", "   │", "└──┘"],
    '4': ["┐  ┐", "│  │", "└──┤", "   │", "   ┘"],
    '5': ["┌── ", "│   ", "└──┐", "   │", "└──┘"],
    '6': ["┌──┐", "│   ", "├──┐", "│  │", "└──┘"],
    '7': ["┌──┐", "   │", "   │", "   │", "   ┘"],
    '8': ["┌──┐", "│  │", "├──┤", "│  │", "└──┘"],
    '9': ["┌──┐", "│  │", "└──┤", "   │", "└──┘"],
    ':': ["    ", " ·  ", "    ", " ·  ", "    "],
}

DIGIT_HEIGHT = 5
DIGIT_WIDTH  = 4


def _render_clock(time_str: str) -> list:
    """
    Render a HH:MM:SS string as 5-row large ASCII block.
    Returns list of 5 strings (one per row).
    """
    rows = [""] * DIGIT_HEIGHT
    for ch in time_str:
        glyph = DIGITS.get(ch, ["    "] * DIGIT_HEIGHT)
        for r in range(DIGIT_HEIGHT):
            rows[r] += glyph[r] + " "
    return rows


# ─── RADAR SCOPE (compact, reused from radar_ui logic) ────

SCOPE_R_Y   = 12
SCOPE_R_X   = int(SCOPE_R_Y * 1.8)
RING_RATIOS = [0.4, 0.75, 1.0]
RING_CHAR   = "·"
CENTRE_CHAR = "⊕"


def _make_scope(radar, aircraft):
    """Build compact radar scope grid with aircraft plotted."""
    rows = SCOPE_R_Y * 2 + 1
    cols = SCOPE_R_X * 2 + 1
    grid = [[" "] * cols for _ in range(rows)]
    cy, cx = SCOPE_R_Y, SCOPE_R_X

    # Draw rings
    for row in range(rows):
        for col in range(cols):
            ny = (row - cy) / SCOPE_R_Y
            nx = (col - cx) / SCOPE_R_X
            dist = math.sqrt(nx * nx + ny * ny)
            if dist > 1.02:
                continue
            for ratio in RING_RATIOS:
                if abs(dist - ratio) < 0.04:
                    grid[row][col] = RING_CHAR
                    break

    # Cardinal axes
    for r in range(1, SCOPE_R_Y + 1):
        if grid[cy - r][cx] == " ": grid[cy - r][cx] = "┊"
        if grid[cy + r][cx] == " ": grid[cy + r][cx] = "┊"
    for r in range(1, SCOPE_R_X + 1):
        if grid[cy][cx + r] == " ": grid[cy][cx + r] = "╌"
        if grid[cy][cx - r] == " ": grid[cy][cx - r] = "╌"

    grid[cy][cx] = CENTRE_CHAR

    # Plot aircraft
    if radar and aircraft:
        clat = (radar.bbox["lat_min"] + radar.bbox["lat_max"]) / 2
        clon = (radar.bbox["lon_min"] + radar.bbox["lon_max"]) / 2
        lat_range = radar.bbox["lat_max"] - radar.bbox["lat_min"]
        lon_range = radar.bbox["lon_max"] - radar.bbox["lon_min"]

        for ac in aircraft:
            ny = (ac.lat - clat) / (lat_range / 2)
            nx = (ac.lon - clon) / (lon_range / 2)
            if nx ** 2 + ny ** 2 > 1.0:
                continue
            col = cx + int(nx * SCOPE_R_X)
            row = cy - int(ny * SCOPE_R_Y)
            if 0 <= row < rows and 0 <= col < cols:
                grid[row][col] = ac.direction_arrow()

    return ["".join(grid[r]) for r in range(rows)]


class AmbientUI:
    """
    BLOC ambient / screensaver mode.

    Layout (side by side):
      LEFT  — large ASCII clock + date
      RIGHT — compact radar scope + contact count

    Below both:
      — active task list (dimmed)

    Exit: q or ESC
    """

    def __init__(self, vault, radar: Radar, env):
        self.vault   = vault
        self.radar   = radar
        self.env     = env
        self._aircraft  = []
        self._radar_age = 0
        self._running   = False

    # ─── entry point ──────────────────────────────────────

    def run(self):
        self._running = True

        # Initial radar fetch in background so we don't block entry
        self.env.clear()
        self.env.dim("    ◈ AMBIENT ············· ACQUIRING")
        t = threading.Thread(target=self._fetch_radar, daemon=True)
        t.start()
        t.join(timeout=12)   # wait up to 12s then proceed with empty scope

        self._loop()

    # ─── radar fetch ──────────────────────────────────────

    def _fetch_radar(self):
        self.radar.fetch_once()
        ac, upd, _ = self.radar.snapshot()
        self._aircraft  = ac
        self._radar_age = upd

    # ─── main loop ────────────────────────────────────────

    def _loop(self):
        while self._running:
            self._draw()
            time.sleep(1)   # redraw every second for clock

            if _kbhit():
                key = _getch()
                if key in ('q', 'Q', '\x1b'):   # q, Q, or ESC
                    self._running = False

        self.env.clear()

    # ─── draw ─────────────────────────────────────────────

    def _draw(self):
        now      = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%a %d %b %Y").upper()

        clock_rows = _render_clock(time_str)
        scope_rows = _make_scope(self.radar, self._aircraft)

        tasks = self.vault.list_tasks()
        ac_count = len([a for a in self._aircraft if not a.on_ground])

        if self._radar_age:
            age_secs = int(time.time() - self._radar_age)
            age_str  = f"+{age_secs:03d}s"
        else:
            age_str = "------"

        self.env.clear()

        # ── top strip ─────────────────────────────────────
        self.env.dim(
            f"    ◈ BLOC OS  ·  AMBIENT"
            f"    {date_str}"
            f"    [{ac_count:02d} CONTACTS]"
            f"    [DATA {age_str}]"
        )
        self.env.separator("double")
        print()

        # ── clock + scope side by side ────────────────────
        scope_height = len(scope_rows)   # SCOPE_R_Y*2+1 = 25
        clock_height = DIGIT_HEIGHT      # 5

        # Pad clock rows to same height as scope with vertical centering
        pad_top    = (scope_height - clock_height) // 2
        pad_bottom = scope_height - clock_height - pad_top

        clock_padded = (
            [""] * pad_top
            + clock_rows
            + [""] * pad_bottom
        )

        # Clock column width
        clock_col_w = len(clock_rows[0]) + 6   # +6 for left margin + gap

        for i in range(scope_height):
            # Left: clock
            if i == pad_top - 2 and date_str:
                # Date label just above clock
                clock_line = f"    {date_str}"
            elif 0 <= i - pad_top < clock_height:
                clock_line = f"    {clock_padded[i]}"
            elif i == pad_top + clock_height + 1:
                # Mission status below clock
                task_str = f"{len(tasks):02d} OBJECTIVES"
                clock_line = f"    {task_str}"
            else:
                clock_line = ""

            # Pad clock column to fixed width
            clock_line = clock_line.ljust(clock_col_w + 4)

            # Right: scope
            scope_line = scope_rows[i] if i < len(scope_rows) else ""

            # Print combined — clock dim, scope slightly brighter
            if 0 <= i - pad_top < clock_height:
                self.env.accent(f"{clock_line}", end="")
            else:
                self.env.dim(f"{clock_line}", end="")

            self.env.dim(f"  {scope_line}")

        # ── task list ─────────────────────────────────────
        print()
        self.env.separator("dot")

        if not tasks:
            self.env.dim("    ◈ OBJECTIVES ············· CLEAR")
        else:
            # Show up to 6 tasks in two columns
            col_tasks = tasks[:12]
            mid       = math.ceil(len(col_tasks) / 2)
            left_col  = col_tasks[:mid]
            right_col = col_tasks[mid:]

            for i in range(mid):
                left  = f"    ▢  {left_col[i][:36]:<36}" if i < len(left_col) else ""
                right = f"  ▢  {right_col[i][:36]}" if i < len(right_col) else ""
                self.env.dim(f"{left}{right}")

        # ── footer ────────────────────────────────────────
        print()
        self.env.separator("double")
        self.env.dim("    q / ESC  EXIT AMBIENT")