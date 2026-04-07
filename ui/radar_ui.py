import time
import math
import os
import sys
from datetime import datetime
from core.radar import Radar, LONDON_TMA

if os.name == 'nt':
    import msvcrt
    def _getch(): return msvcrt.getwch()
else:
    import tty, termios
    def _getch():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ─── SCOPE GEOMETRY ───────────────────────────────────────
#
#  Terminal chars are ~2x taller than wide, so we correct
#  by making the scope grid wider than tall.
#  SCOPE_R_Y = vertical radius (rows)
#  SCOPE_R_X = horizontal radius (cols) — stretched ~1.8x
#
SCOPE_R_Y   = 18          # rows  — increase for bigger scope
SCOPE_R_X   = int(SCOPE_R_Y * 1.8)   # ~32 cols
RING_RATIOS = [0.35, 0.65, 1.0]      # range rings as fraction of radius

RING_CHAR   = "·"
CENTRE_CHAR = "⊕"
N_LABEL     = "N"


def _make_scope_grid():
    """
    Build a 2-D character grid of the blank radar scope.
    Grid is indexed [row][col].  Centre is (SCOPE_R_Y, SCOPE_R_X).
    """
    rows = SCOPE_R_Y * 2 + 1
    cols = SCOPE_R_X * 2 + 1
    grid = [[" "] * cols for _ in range(rows)]
    cy, cx = SCOPE_R_Y, SCOPE_R_X

    for row in range(rows):
        for col in range(cols):
            # Normalise to ellipse space
            ny = (row - cy) / SCOPE_R_Y
            nx = (col - cx) / SCOPE_R_X
            dist = math.sqrt(nx * nx + ny * ny)   # 0..1 within scope

            if dist > 1.02:
                continue   # outside scope — leave blank

            # Range rings
            for ratio in RING_RATIOS:
                if abs(dist - ratio) < 0.03:
                    grid[row][col] = RING_CHAR
                    break

    # Cardinal axis lines (faint)
    for r in range(1, SCOPE_R_Y + 1):
        if grid[cy - r][cx] == " ":
            grid[cy - r][cx] = "┊"
        if grid[cy + r][cx] == " ":
            grid[cy + r][cx] = "┊"
    for r in range(1, SCOPE_R_X + 1):
        if grid[cy][cx + r] == " ":
            grid[cy][cx + r] = "╌"
        if grid[cy][cx - r] == " ":
            grid[cy][cx - r] = "╌"

    # N label just above top of scope
    grid[cy - SCOPE_R_Y][cx] = N_LABEL

    # Centre marker
    grid[cy][cx] = CENTRE_CHAR
    return grid


def _place_aircraft(grid, radar, aircraft):
    """
    Plot each aircraft onto the grid.
    Returns list of (row, col, Aircraft) for sidebar mapping.
    """
    cy, cx = SCOPE_R_Y, SCOPE_R_X
    rows   = SCOPE_R_Y * 2 + 1
    cols   = SCOPE_R_X * 2 + 1
    plotted = []

    clat = (radar.bbox["lat_min"] + radar.bbox["lat_max"]) / 2
    clon = (radar.bbox["lon_min"] + radar.bbox["lon_max"]) / 2
    lat_range = radar.bbox["lat_max"] - radar.bbox["lat_min"]
    lon_range = radar.bbox["lon_max"] - radar.bbox["lon_min"]

    for ac in aircraft:
        # Normalise lat/lon to [-1, 1]
        ny = (ac.lat - clat) / (lat_range / 2)
        nx = (ac.lon - clon) / (lon_range / 2)

        # Skip if outside unit ellipse
        if nx ** 2 + ny ** 2 > 1.0:
            continue

        col = cx + int(nx * SCOPE_R_X)
        row = cy - int(ny * SCOPE_R_Y)   # screen y inverted

        if 0 <= row < rows and 0 <= col < cols:
            grid[row][col] = ac.direction_arrow()
            plotted.append((row, col, ac))

    return plotted


class RadarUI:
    """
    Static radar scope — data loads on entry and on manual refresh (r).
    No background thread, no animation — one API call per r keypress.

    Controls:
      r  — fetch fresh data from OpenSky
      f  — toggle filter (hide ground traffic)
      s  — toggle scope / traffic list
      j/k — scroll list
      q  — back to shell
    """

    def __init__(self, radar: Radar, env):
        self.radar         = radar
        self.env           = env
        self.filter_ground = False
        self.show_list     = False
        self.selected      = 0
        self._aircraft     = []
        self._updated      = 0.0
        self._error        = ""
        self._fetching     = False

    # ─── entry point ──────────────────────────────────────

    def run(self):
        self.env.clear()
        self.env.accent("  ◈ RADAR  ◀  LONDON TMA ·········· OPENING CHANNEL")
        self.env.dim("  ◈ FETCHING INITIAL SWEEP ·········· STAND BY")

        self._do_fetch()   # blocking fetch on entry
        self._main_loop()

    # ─── fetch (blocking, called manually) ────────────────

    def _do_fetch(self):
        self._fetching = True
        self.radar.fetch_once()
        ac, upd, err = self.radar.snapshot()
        self._aircraft = ac
        self._updated  = upd
        self._error    = err
        self._fetching = False

    # ─── main loop — wait for keypress, redraw ─────────────

    def _main_loop(self):
        self._draw()
        while True:
            key = _getch().lower()

            if key == 'q':
                self.env.clear()
                return

            elif key == 'r':
                self.env.clear()
                self.env.accent("  ◈ RADAR  ◀  REFRESHING ············ STAND BY")
                self._do_fetch()
                self._draw()

            elif key == 'f':
                self.filter_ground = not self.filter_ground
                self._draw()

            elif key == 's':
                self.show_list = not self.show_list
                self.selected  = 0
                self._draw()

            elif key in ('j',):
                self.selected += 1
                self._draw()

            elif key in ('k',):
                self.selected = max(0, self.selected - 1)
                self._draw()

    # ─── top-level draw ───────────────────────────────────

    def _draw(self):
        aircraft = self._aircraft
        if self.filter_ground:
            aircraft = [a for a in aircraft if not a.on_ground]

        self.env.clear()
        self._draw_header(len(aircraft))

        if self.show_list:
            self._draw_list(aircraft)
        else:
            self._draw_scope(aircraft)

        self._draw_footer()

    # ─── header ───────────────────────────────────────────

    def _draw_header(self, count):
        now = datetime.now().strftime("%H:%M:%S")
        age = ""
        if self._updated:
            secs = int(time.time() - self._updated)
            age  = f"  +{secs:03d}s AGO"

        err_flag = "  ERR" if self._error else ""
        flt_flag = "  GND-FILT" if self.filter_ground else ""

        self.env.accent(
            f"  ◈ RADAR  ◀  LONDON TMA"
            f"    {now}{age}"
            f"    {count:02d} CONTACTS{flt_flag}{err_flag}"
        )
        self.env.separator()

        if self._error:
            self.env.alert(f"  ◈ LINK ERROR ·· {self._error}")
            self.env.separator()

    # ─── scope view ───────────────────────────────────────

    def _draw_scope(self, aircraft):
        grid    = _make_scope_grid()
        plotted = _place_aircraft(grid, self.radar, aircraft)

        rows    = SCOPE_R_Y * 2 + 1
        cols    = SCOPE_R_X * 2 + 1
        cy      = SCOPE_R_Y

        # Build sidebar — aircraft sorted by altitude, max rows = scope height
        sidebar = aircraft[:rows]
        self.selected = min(self.selected, max(0, len(sidebar) - 1))

        for row_idx in range(rows):
            row_str = "".join(grid[row_idx])

            # Scope line — equator brighter
            if row_idx == cy:
                self.env.primary(f"  {row_str}  ", end="")
            else:
                self.env.dim(f"  {row_str}  ", end="")

            # Sidebar entry alongside
            si = row_idx - 1   # slight top offset
            if 0 <= si < len(sidebar):
                ac     = sidebar[si]
                arrow  = ac.direction_arrow()
                marker = "▶ " if si == self.selected else "  "
                entry  = (
                    f"{marker}{arrow} {ac.callsign:<9}"
                    f"{ac.fl:<7}"
                    f"{ac.speed_kt:>3}kt"
                )
                if si == self.selected:
                    self.env.accent(entry)
                elif ac.on_ground:
                    self.env.dim(entry)
                else:
                    self.env.primary(entry)
            else:
                print()

        # Overflow sidebar rows below scope
        for si in range(rows - 1, len(sidebar)):
            ac    = sidebar[si]
            arrow = ac.direction_arrow()
            pad   = " " * (cols + 4)
            marker = "▶ " if si == self.selected else "  "
            entry  = (
                f"{pad}{marker}{arrow} {ac.callsign:<9}"
                f"{ac.fl:<7}"
                f"{ac.speed_kt:>3}kt"
            )
            if si == self.selected:
                self.env.accent(entry)
            else:
                self.env.dim(entry)

    # ─── list view ────────────────────────────────────────

    def _draw_list(self, aircraft):
        self.env.dim(
            f"  {'':>2}  {'CALLSIGN':<10}{'ICAO':<8}"
            f"{'FL':>6}  {'SPD':>5}  {'HDG':>5}  DIR  STATUS"
        )
        self.env.separator("dot")

        if not aircraft:
            self.env.dim("  ◈ NO CONTACTS IN TMA")
            return

        self.selected = min(self.selected, len(aircraft) - 1)
        max_rows = 24
        start    = max(0, self.selected - max_rows // 2)
        visible  = aircraft[start : start + max_rows]

        for i, ac in enumerate(visible):
            idx    = start + i
            arrow  = ac.direction_arrow()
            status = "GND" if ac.on_ground else "AIR"
            marker = "▶" if idx == self.selected else " "
            line   = (
                f"  {marker} {ac.callsign:<10}{ac.icao:<8}"
                f"{ac.fl:>6}  {ac.speed_kt:>4}kt"
                f"  {int(ac.track_deg):>4}°"
                f"  {arrow}    {status}"
            )
            if idx == self.selected:
                self.env.accent(line)
            elif ac.on_ground:
                self.env.dim(line)
            else:
                self.env.primary(line)

        if len(aircraft) > max_rows:
            self.env.dim(
                f"\n  ◈ {start+1}–{start+len(visible)} OF {len(aircraft)}"
                f"  ·  j / k  TO SCROLL"
            )

    # ─── footer ───────────────────────────────────────────

    def _draw_footer(self):
        view = "LIST" if self.show_list else "SCOPE"
        print()
        self.env.separator()
        self.env.dim(
            f"  r REFRESH  ·  f FILTER GND  ·  s {view}/{'SCOPE' if self.show_list else 'LIST'}"
            f"  ·  j/k SCROLL  ·  q BACK"
        )