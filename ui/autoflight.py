"""
autoflight.py — BLOC AUTOFLIGHT / TRAFFIC MODE
───────────────────────────────────────────────
Pygame full-screen ATC display for Pi 5.
No mouse. Keyboard commands only.
Manual refresh only (command: r).

Layout mirrors the ATC screenshot:
  ┌─────────────────────────────────────────────────────┐
  │  TOP BAR  —  clock · callsign · sector · ac count   │
  ├──────────────┬──────────────────────┬───────────────┤
  │  STRIPS LEFT │   RADAR CENTRE       │  OBJECTIVES   │
  │  incoming    │   London TMA map     │  right panel  │
  │  active      │   blips · sweep      │               │
  │  landed      │                      │               │
  ├──────────────┴──────────────────────┴───────────────┤
  │  BOTTOM — INCOMING · ACTIVE · LANDED · COMPASS      │
  └─────────────────────────────────────────────────────┘

Commands (no mouse):
  r  — manual refresh (OpenSky + vault)
  q  — quit back to shell
  ↑↓ — scroll objectives list
  ESC — quit

Data colour coding (full ATC palette):
  #00FF41  green  — primary / landed / done
  #00E5FF  cyan   — commercial aircraft / incoming tasks
  #FFB000  amber  — active tasks / in-sector / warnings
  #4488FF  blue   — time data / day progress
  #FF3333  red    — critical / overdue
"""

import os
import sys
import math
import time
import threading
import urllib.request
import json
from datetime import datetime
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = os.environ.get("SDL_VIDEODRIVER", "")
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame

# ═══════════════════════════════════════════════════════════
#  COLOUR PALETTE
# ═══════════════════════════════════════════════════════════

C = {
    "bg":          (0,   10,  2),
    "bg2":         (0,   14,  3),
    "panel":       (0,   12,  3),
    "border":      (0,  255,  65, 25),
    "border2":     (0,  255,  65, 50),

    "green":       (0,  255,  65),
    "green2":      (0,  180,  45),
    "green_dim":   (0,   90,  22),
    "green_dark":  (0,   30,   8),

    "cyan":        (0,  229, 255),
    "cyan2":       (0,  150, 180),
    "cyan_dim":    (0,   60,  80),

    "blue":        (68, 136, 255),
    "blue2":       (34,  80, 200),
    "blue_dim":    (15,  35,  80),

    "amber":       (255, 176,   0),
    "amber2":      (200, 130,   0),
    "amber_dim":   (60,  38,   0),

    "red":         (255,  50,  50),
    "white":       (220, 220, 210),
    "dim":         (40,   60,  40),
}

# ═══════════════════════════════════════════════════════════
#  LONDON TMA — BOUNDING BOX + MAP SHAPE
# ═══════════════════════════════════════════════════════════

BBOX = {
    "lat_min": 51.0, "lat_max": 52.0,
    "lon_min": -1.0, "lon_max":  0.6,
}

# Simplified London/SE England coastline + TMA boundary
# Normalised [0..1] in lon,lat order (lon=x, lat=y)
# lat_min=51.0, lat_max=52.0 → y:  0=south, 1=north
# lon_min=-1.0, lon_max=0.6  → x:  0=west,  1=east

TMA_BOUNDARY = [
    (0.30, 0.18), (0.38, 0.12), (0.50, 0.10), (0.62, 0.13),
    (0.72, 0.20), (0.82, 0.30), (0.85, 0.42), (0.82, 0.54),
    (0.75, 0.64), (0.65, 0.72), (0.52, 0.76), (0.40, 0.74),
    (0.28, 0.68), (0.20, 0.58), (0.18, 0.46), (0.20, 0.34),
    (0.25, 0.24), (0.30, 0.18),
]

TMA_INNER = [
    (0.42, 0.34), (0.50, 0.28), (0.58, 0.32), (0.63, 0.40),
    (0.61, 0.50), (0.54, 0.56), (0.46, 0.54), (0.40, 0.47),
    (0.40, 0.38), (0.42, 0.34),
]

# London borough coastline silhouette (Thames path, simplified)
THAMES_PATH = [
    (0.28, 0.50), (0.35, 0.52), (0.42, 0.50), (0.48, 0.49),
    (0.54, 0.48), (0.60, 0.47), (0.66, 0.46), (0.72, 0.48),
    (0.76, 0.52),
]

AIRPORTS = [
    {"name": "LHR", "full": "HEATHROW", "lon": -0.454, "lat": 51.477},
    {"name": "LGW", "full": "GATWICK",  "lon": -0.190, "lat": 51.148},
    {"name": "STN", "full": "STANSTED", "lon":  0.235, "lat": 51.885},
    {"name": "LTN", "full": "LUTON",    "lon": -0.368, "lat": 51.874},
    {"name": "LCY", "full": "CITY",     "lon":  0.055, "lat": 51.505},
]

WAYPOINTS = [
    {"name": "LUCAS", "lon": -0.10, "lat": 51.12},
    {"name": "POLKA", "lon":  0.40, "lat": 51.12},
    {"name": "PIANO", "lon":  0.10, "lat": 51.95},
    {"name": "LEKOS", "lon":  0.50, "lat": 51.82},
    {"name": "CHALI", "lon": -0.80, "lat": 51.12},
    {"name": "LOTTO", "lon":  0.55, "lat": 51.50},
    {"name": "RCSS",  "lon":  0.20, "lat": 51.50},
    {"name": "BEGTO", "lon": -0.90, "lat": 51.50},
]

OPENSKY_URL = (
    "https://opensky-network.org/api/states/all"
    "?lamin={lat_min}&lamax={lat_max}&lomin={lon_min}&lomax={lon_max}"
)

# ═══════════════════════════════════════════════════════════
#  GEO HELPERS
# ═══════════════════════════════════════════════════════════

def geo_to_norm(lon, lat):
    """Convert lon/lat to normalised [0,1] in bbox."""
    x = (lon - BBOX["lon_min"]) / (BBOX["lon_max"] - BBOX["lon_min"])
    y = 1.0 - (lat - BBOX["lat_min"]) / (BBOX["lat_max"] - BBOX["lat_min"])
    return x, y


def norm_to_px(nx, ny, rect):
    """Map normalised coords to pixel rect (x,y,w,h)."""
    return (
        int(rect[0] + nx * rect[2]),
        int(rect[1] + ny * rect[3]),
    )


# ═══════════════════════════════════════════════════════════
#  AIRCRAFT DATA
# ═══════════════════════════════════════════════════════════

class Aircraft:
    __slots__ = ("icao","callsign","lat","lon","alt_m","spd_ms","track","on_ground")

    def __init__(self, s):
        self.icao      = (s[0] or "??????").upper()
        self.callsign  = (s[1] or "").strip().upper() or self.icao
        self.lon       = s[5]
        self.lat       = s[6]
        self.alt_m     = s[7] or 0
        self.spd_ms    = s[9] or 0
        self.track     = s[10] or 0
        self.on_ground = bool(s[8])

    @property
    def alt_ft(self): return int(self.alt_m * 3.281)
    @property
    def spd_kt(self): return int(self.spd_ms * 1.944)
    @property
    def fl(self):
        if self.on_ground: return "GND"
        return f"FL{self.alt_ft//100:03d}"


# ═══════════════════════════════════════════════════════════
#  OPENSKY FETCHER
# ═══════════════════════════════════════════════════════════

class OpenSkyFetcher:
    def __init__(self):
        self.aircraft   = []
        self.last_fetch = 0.0
        self.error      = ""
        self._lock      = threading.Lock()
        self._fetching  = False

    def fetch(self, callback=None):
        """Non-blocking fetch in background thread."""
        if self._fetching:
            return
        self._fetching = True
        t = threading.Thread(target=self._do_fetch, args=(callback,), daemon=True)
        t.start()

    def snapshot(self):
        with self._lock:
            return list(self.aircraft), self.last_fetch, self.error

    def _do_fetch(self, callback):
        url = OPENSKY_URL.format(**BBOX)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BLOC-OS/0.1"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
            states = data.get("states") or []
            parsed = []
            for s in states:
                try:
                    ac = Aircraft(s)
                    if ac.lat is not None and ac.lon is not None:
                        if not ac.on_ground:
                            parsed.append(ac)
                except Exception:
                    pass
            parsed.sort(key=lambda a: a.alt_m, reverse=True)
            with self._lock:
                self.aircraft  = parsed[:80]  # cap for performance
                self.last_fetch = time.time()
                self.error      = ""
        except Exception as e:
            with self._lock:
                self.error = str(e)[:50]
        finally:
            self._fetching = False
        if callback:
            callback()


# ═══════════════════════════════════════════════════════════
#  VAULT TASK READER
# ═══════════════════════════════════════════════════════════

def load_tasks(vault_root: Path):
    """
    Read tasks from inbox.md — same format vault.py writes.
    Returns list of dicts: {title, done, due, tags}
    """
    inbox = vault_root / "tasks" / "inbox.md"
    tasks = []
    if not inbox.exists():
        return tasks
    for line in inbox.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("- ["):
            continue
        done  = line.startswith("- [x]") or line.startswith("- [X]")
        title = line[5:].strip()
        # strip inline metadata  **due:** ...  **tags:** ...
        import re
        due_m = re.search(r"\*\*due:\*\*\s*(\S+)", title)
        due   = due_m.group(1) if due_m else ""
        title = re.sub(r"\s*\*\*due:\*\*\s*\S+", "", title)
        title = re.sub(r"\s*\*\*tags:\*\*\s*.*", "", title).strip()
        tasks.append({"title": title, "done": done, "due": due})
    return tasks


# ═══════════════════════════════════════════════════════════
#  AUTOFLIGHT DISPLAY
# ═══════════════════════════════════════════════════════════

class AutoflightDisplay:

    TOP_H    = 26
    BOT_H    = 52
    STRIP_W  = 192
    RIGHT_W  = 210

    def __init__(self, vault_root: Path, config=None, callsign="ADMIN-1"):
        pygame.init()
        pygame.display.set_caption("BLOC · AUTOFLIGHT")

        info = pygame.display.Info()
        self.W = info.current_w
        self.H = info.current_h

        # Full-screen on Pi; windowed on Windows dev machine
        import platform
        if platform.system() == "Windows":
            # Windowed on Windows — easier to escape during dev
            self.W, self.H = 1280, 720
            self.screen = pygame.display.set_mode((self.W, self.H), pygame.RESIZABLE)
        else:
            flags = pygame.FULLSCREEN | pygame.NOFRAME
            try:
                self.screen = pygame.display.set_mode((self.W, self.H), flags)
            except Exception:
                self.W, self.H = 1280, 720
                self.screen = pygame.display.set_mode((self.W, self.H))

        pygame.mouse.set_visible(False)

        self.vault_root = vault_root
        self.callsign   = callsign
        self.clock      = pygame.time.Clock()
        self.running    = True

        # Fonts — Share Tech Mono feel; fallback to monospace
        mono = self._find_mono_font()
        self.font_sm  = pygame.font.Font(mono, 10)
        self.font_md  = pygame.font.Font(mono, 12)
        self.font_lg  = pygame.font.Font(mono, 14)
        self.font_xl  = pygame.font.Font(mono, 18)

        # OpenSky
        self.fetcher      = OpenSkyFetcher()
        self.aircraft     = []
        self.fetch_ts     = 0.0
        self.fetch_error  = ""
        self.fetching     = False

        # Tasks
        self.tasks        = []
        self.obj_scroll   = 0

        # Sweep animation
        self.sweep_angle  = 0.0   # radians
        self.sweep_speed  = 0.4   # radians/sec  (≈15s per rotation)

        # Phosphor trail buffer — list of (x,y,age) in radar pixels
        self.trails       = []     # [(x,y,alpha)]

        # Radar rect (computed in layout)
        self.radar_rect   = None

        # Status
        self.status_msg   = "AUTOFLIGHT ENGAGED · PRESS r TO REFRESH · q TO EXIT"
        self.status_ts    = time.time()

        # Initial load
        self._refresh()

    # ── FONT DISCOVERY ────────────────────────────────────

    def _find_mono_font(self):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
            "/System/Library/Fonts/Menlo.ttc",
            "C:/Windows/Fonts/consola.ttf",
        ]
        for p in candidates:
            if Path(p).exists():
                return p
        return pygame.font.match_font("dejavusansmono,liberationmono,couriernew,monospace")

    # ── LAYOUT HELPERS ────────────────────────────────────

    @property
    def radar_rect(self):
        return self._radar_rect

    @radar_rect.setter
    def radar_rect(self, v):
        self._radar_rect = v

    def _layout(self):
        """Compute all layout rects from current W,H."""
        T, B, S, R = self.TOP_H, self.BOT_H, self.STRIP_W, self.RIGHT_W
        mid_h = self.H - T - B
        radar_w = self.W - S - R
        self._radar_rect   = pygame.Rect(S, T, radar_w, mid_h)
        self._strip_rect   = pygame.Rect(0, T, S, mid_h)
        self._right_rect   = pygame.Rect(self.W - R, T, R, mid_h)
        self._top_rect     = pygame.Rect(0, 0, self.W, T)
        self._bot_rect     = pygame.Rect(0, self.H - B, self.W, B)

    # ── REFRESH ───────────────────────────────────────────

    def _refresh(self):
        self.tasks = load_tasks(self.vault_root)
        self.fetching = True
        self.status_msg = "ACQUIRING TRAFFIC DATA ···"
        self.fetcher.fetch(callback=self._on_fetch_done)

    def _on_fetch_done(self):
        self.aircraft, self.fetch_ts, self.fetch_error = self.fetcher.snapshot()
        n = len(self.aircraft)
        ts = datetime.fromtimestamp(self.fetch_ts).strftime("%H:%M:%S") if self.fetch_ts else "--:--"
        if self.fetch_error:
            self.status_msg = f"FETCH FAULT · {self.fetch_error}"
        else:
            self.status_msg = f"TRAFFIC UPDATED · {n} CONTACTS · {ts} · NEXT REFRESH: MANUAL [r]"
        self.fetching = False

    # ── MAIN LOOP ─────────────────────────────────────────

    def run(self):
        self._layout()
        while self.running:
            dt = self.clock.tick(30) / 1000.0
            self._handle_events()
            self._update(dt)
            self._draw()
            pygame.display.flip()
        pygame.quit()

    def _handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.VIDEORESIZE:
                self.W, self.H = ev.w, ev.h
                self.screen = pygame.display.set_mode((self.W, self.H), pygame.RESIZABLE)
                self._layout()
            elif ev.type == pygame.KEYDOWN:
                alt = pygame.key.get_mods() & pygame.KMOD_ALT
                if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                    self.running = False
                elif ev.key == pygame.K_F4 and alt:
                    self.running = False
                elif ev.key == pygame.K_r:
                    self._refresh()
                elif ev.key == pygame.K_UP:
                    self.obj_scroll = max(0, self.obj_scroll - 1)
                elif ev.key == pygame.K_DOWN:
                    self.obj_scroll += 1


    def _update(self, dt):
        self.sweep_angle = (self.sweep_angle + self.sweep_speed * dt) % (math.pi * 2)

    # ── DRAWING ───────────────────────────────────────────

    def _draw(self):
        self.screen.fill(C["bg"])
        self._draw_top_bar()
        self._draw_radar()
        self._draw_strip_panel()
        self._draw_right_panel()
        self._draw_bottom_bar()

    # ── HELPERS ───────────────────────────────────────────

    def _text(self, surf, text, pos, color, font=None, anchor="topleft"):
        f = font or self.font_sm
        s = f.render(str(text), True, color)
        r = s.get_rect(**{anchor: pos})
        surf.blit(s, r)
        return r

    def _hline(self, surf, y, x0=0, x1=None, color=None, alpha=60):
        c = color or C["green"]
        x1 = x1 or self.W
        pygame.draw.line(surf, _dim(c, alpha), (x0, y), (x1, y), 1)

    def _vline(self, surf, x, y0=0, y1=None, color=None, alpha=60):
        c = color or C["green"]
        y1 = y1 or self.H
        pygame.draw.line(surf, _dim(c, alpha), (x, y0), (x, y1), 1)

    def _panel_bg(self, surf, rect, alpha=180):
        s = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        s.fill((*C["panel"], alpha))
        surf.blit(s, rect.topleft)

    # ── TOP BAR ───────────────────────────────────────────

    def _draw_top_bar(self):
        r = self._top_rect
        pygame.draw.rect(self.screen, C["bg2"], r)
        self._hline(self.screen, r.bottom - 1, alpha=80)

        now = datetime.now().strftime("%H:%M:%S")
        ts  = datetime.fromtimestamp(self.fetch_ts).strftime("%H:%M") if self.fetch_ts else "--:--"
        n   = len(self.aircraft)

        x = 10
        items = [
            ("MODE",    "AUTOFLIGHT",             C["amber"]),
            ("SECTOR",  "LONDON TMA",             C["cyan"]),
            ("TRAFFIC", f"{n:02d} AC",            C["green"]),
            ("UPDATED", ts,                        C["green_dim"]),
        ]
        for label, val, col in items:
            self._text(self.screen, label, (x, 5), C["green_dim"], self.font_sm)
            self._text(self.screen, val, (x, 14), col, self.font_sm)
            x += max(len(val), len(label)) * 7 + 20
            self._vline(self.screen, x - 10, 4, r.bottom - 4, alpha=40)

        # Centre clock
        self._text(self.screen, now, (self.W // 2, r.centery),
                   C["green"], self.font_lg, anchor="center")

        # Right: callsign + status hint
        self._text(self.screen, f"[r] REFRESH  [↑↓] SCROLL  [q] EXIT",
                   (self.W - 10, 5), C["green_dim"], self.font_sm, anchor="topright")
        self._text(self.screen, self.callsign,
                   (self.W - 10, 14), C["green"], self.font_sm, anchor="topright")

        # Status strip below bar — only if fetching
        if self.fetching:
            dots = "·" * (int(time.time() * 4) % 12)
            msg = f"  ACQUIRING {dots}"
            self._text(self.screen, msg, (self.W//2, r.bottom - 12),
                       C["amber"], self.font_sm, anchor="center")

    # ── RADAR ─────────────────────────────────────────────

    def _draw_radar(self):
        r = self._radar_rect
        self._panel_bg(self.screen, r, alpha=200)

        # Grid
        self._draw_radar_grid(r)

        # TMA polygon
        self._draw_tma(r)

        # Thames
        self._draw_thames(r)

        # Range rings
        self._draw_range_rings(r)

        # Waypoint triangles
        self._draw_waypoints(r)

        # Airports
        self._draw_airports(r)

        # Sweep
        self._draw_sweep(r)

        # Aircraft blips
        self._draw_aircraft(r)

        # Border
        pygame.draw.rect(self.screen, _dim(C["green"], 60), r, 1)

        # Status line inside radar (bottom)
        msg = self.status_msg
        self._text(self.screen, msg,
                   (r.left + 6, r.bottom - 14),
                   C["green_dim"], self.font_sm)

        # Coord labels top edge
        for i, lon in enumerate([-0.8, -0.4, 0.0, 0.4]):
            x, _ = geo_to_norm(lon, 51.5)
            px = int(r.left + x * r.w)
            self._text(self.screen, f"{lon:+.1f}", (px, r.top + 2),
                       _dim(C["green"], 60), self.font_sm)

    def _draw_radar_grid(self, r):
        step = 40
        s = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        for x in range(0, r.w, step):
            pygame.draw.line(s, (0, 255, 65, 12), (x, 0), (x, r.h))
        for y in range(0, r.h, step):
            pygame.draw.line(s, (0, 255, 65, 12), (0, y), (r.w, y))
        self.screen.blit(s, r.topleft)

    def _draw_tma(self, r):
        def pts(poly):
            return [norm_to_px(*p, (r.left, r.top, r.w, r.h)) for p in poly]

        s = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        outer_pts = [(_p[0] - r.left, _p[1] - r.top) for _p in pts(TMA_BOUNDARY)]
        pygame.draw.polygon(s, (0, 80, 30, 25), outer_pts)
        pygame.draw.polygon(s, (0, 255, 65,  0), outer_pts)
        self.screen.blit(s, r.topleft)
        pygame.draw.polygon(self.screen, _dim(C["green2"], 45),
                             pts(TMA_BOUNDARY), 1)
        pygame.draw.polygon(self.screen, _dim(C["cyan"], 30),
                             pts(TMA_INNER), 1)

    def _draw_thames(self, r):
        pts = [norm_to_px(*geo_to_norm(p[0], p[1]),
               (r.left, r.top, r.w, r.h)) for p in
               [(-0.50,51.47),(-0.35,51.49),(-0.18,51.50),
                ( 0.00,51.50),( 0.15,51.51),( 0.30,51.52)]]
        if len(pts) >= 2:
            pygame.draw.lines(self.screen, _dim(C["blue2"], 60), False, pts, 1)

    def _draw_range_rings(self, r):
        cx = r.left + r.w // 2
        cy = r.top  + r.h // 2
        # Radius in pixels for 50nm increments
        # 1 degree lat ≈ 111km ≈ 60nm; bbox height ≈ 1deg lat
        nm_per_px = 60.0 / r.h  # rough
        for nm in [50, 100, 150]:
            px_r = int(nm / nm_per_px)
            if px_r > max(r.w, r.h): continue
            s = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            pygame.draw.circle(s, (0,255,65,15),
                               (cx - r.left, cy - r.top), px_r, 1)
            self.screen.blit(s, r.topleft)
            self._text(self.screen, f"{nm}NM",
                       (cx + px_r - 22, cy - 8),
                       _dim(C["green_dim"], 120), self.font_sm)

    def _draw_waypoints(self, r):
        for wp in WAYPOINTS:
            nx, ny = geo_to_norm(wp["lon"], wp["lat"])
            if not (0.02 < nx < 0.98 and 0.02 < ny < 0.98):
                continue
            px, py = norm_to_px(nx, ny, (r.left, r.top, r.w, r.h))
            # Triangle
            pts = [(px, py-7), (px+4, py+2), (px-4, py+2)]
            pygame.draw.polygon(self.screen, C["green2"], pts)
            self._text(self.screen, wp["name"], (px+6, py-4),
                       C["green_dim"], self.font_sm)

    def _draw_airports(self, r):
        for ap in AIRPORTS:
            nx, ny = geo_to_norm(ap["lon"], ap["lat"])
            if not (0 < nx < 1 and 0 < ny < 1):
                continue
            px, py = norm_to_px(nx, ny, (r.left, r.top, r.w, r.h))
            pygame.draw.rect(self.screen, C["green"], (px-3, py-3, 6, 6), 0)
            self._text(self.screen, ap["name"], (px+6, py-4),
                       C["green2"], self.font_sm)

    def _draw_sweep(self, r):
        cx = r.left + r.w // 2
        cy = r.top  + r.h // 2
        max_r = max(r.w, r.h)

        # Phosphor trail — draw as filled arc segments
        trail_surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        trail_len = math.pi * 0.4
        steps = 28
        for i in range(steps):
            a = self.sweep_angle - (i / steps) * trail_len
            alpha = int((1 - i / steps) ** 1.8 * 28)
            if alpha < 2: continue
            # Thin wedge approximation — line at angle
            ex = cx - r.left + int(math.cos(a) * max_r)
            ey = cy - r.top  + int(math.sin(a) * max_r)
            pygame.draw.line(trail_surf, (0, 255, 65, alpha),
                             (cx - r.left, cy - r.top), (ex, ey), 1)
        self.screen.blit(trail_surf, r.topleft)

        # Sweep arm
        ex = cx + int(math.cos(self.sweep_angle) * max_r)
        ey = cy + int(math.sin(self.sweep_angle) * max_r)
        pygame.draw.line(self.screen, _dim(C["green"], 160),
                         (cx, cy), (ex, ey), 1)

    def _draw_aircraft(self, r):
        for ac in self.aircraft:
            if ac.lat is None or ac.lon is None:
                continue
            nx, ny = geo_to_norm(ac.lon, ac.lat)
            if not (0 < nx < 1 and 0 < ny < 1):
                continue
            px, py = norm_to_px(nx, ny, (r.left, r.top, r.w, r.h))

            # Direction arrow (tiny aircraft shape)
            self._draw_blip(px, py, ac.track, C["cyan"])

            # Trail line behind
            trail_len = 14
            tx = px - int(math.sin(math.radians(ac.track)) * trail_len)
            ty = py + int(math.cos(math.radians(ac.track)) * trail_len)
            pygame.draw.line(self.screen, _dim(C["cyan"], 50), (px, py), (tx, ty), 1)

            # Label — callsign, type, FL on same side
            lx = px + 9
            ly = py - 4
            # Keep label inside radar rect
            if lx + 55 > r.right:
                lx = px - 65
            self._text(self.screen, ac.callsign, (lx, ly),
                       C["cyan"], self.font_sm)
            self._text(self.screen, ac.fl, (lx, ly + 10),
                       C["green_dim"], self.font_sm)
            if ac.spd_kt > 0:
                self._text(self.screen, f"{ac.spd_kt}kt", (lx, ly + 20),
                           _dim(C["green_dim"], 140), self.font_sm)

    def _draw_blip(self, px, py, track_deg, color):
        """Small oriented aircraft shape — 3 points."""
        a = math.radians(track_deg - 90)
        nose  = (px + int(math.cos(a) * 5), py + int(math.sin(a) * 5))
        left  = (px + int(math.cos(a + 2.4) * 4), py + int(math.sin(a + 2.4) * 4))
        right = (px + int(math.cos(a - 2.4) * 4), py + int(math.sin(a - 2.4) * 4))
        pygame.draw.polygon(self.screen, color, [nose, left, right])

    # ── STRIP PANEL (LEFT) ────────────────────────────────

    def _draw_strip_panel(self):
        r = self._strip_rect
        self._panel_bg(self.screen, r)
        self._vline(self.screen, r.right, r.top, r.bottom, alpha=80)

        y = r.top + 4
        self._text(self.screen, "FLIGHT STRIPS", (r.left + 6, y),
                   C["green_dim"], self.font_sm)
        y += 14
        self._hline(self.screen, y, r.left, r.right, alpha=50)
        y += 4

        tasks = self.tasks
        done   = [t for t in tasks if t["done"]]
        active = [t for t in tasks if not t["done"]]

        sections = [
            ("INCOMING",  active[:3],  C["cyan"]),
            ("ACTIVE",    active[3:6], C["amber"]),
            ("LANDED",    done[-4:],   C["green_dim"]),
        ]

        for section_name, items, col in sections:
            # Section header
            pygame.draw.circle(self.screen, col, (r.left + 9, y + 5), 3)
            self._text(self.screen, section_name, (r.left + 16, y),
                       col, self.font_sm)
            y += 14
            self._hline(self.screen, y, r.left, r.right, alpha=30)
            y += 3

            if not items:
                self._text(self.screen, "  NO CONTACTS", (r.left + 8, y),
                           C["green_dark"], self.font_sm)
                y += 14
            else:
                for task in items:
                    if y > r.bottom - 20:
                        break
                    self._draw_strip(r, y, task, col)
                    y += 36

            y += 4

    def _draw_strip(self, panel_r, y, task, col):
        """Draw one flight strip row."""
        x = panel_r.left + 3
        w = panel_r.w - 6
        # Left border line
        pygame.draw.line(self.screen, col, (x, y), (x, y + 32), 2)
        # Callsign
        cs = ("BLK-" + task["title"][:8].upper().replace(" ",""))[:10]
        self._text(self.screen, cs, (x + 5, y + 2), col, self.font_sm)
        # Route
        title = task["title"][:24]
        self._text(self.screen, title, (x + 5, y + 13), C["green_dim"], self.font_sm)
        # Due / status
        status = f"DUE {task['due']}" if task.get("due") else "QUEUED"
        self._text(self.screen, status, (x + 5, y + 24), _dim(col, 140), self.font_sm)
        # Thin bottom border
        pygame.draw.line(self.screen, _dim(C["green"], 25),
                         (x, y + 34), (x + w, y + 34), 1)

    # ── RIGHT PANEL — OBJECTIVES ──────────────────────────

    def _draw_right_panel(self):
        r = self._right_rect
        self._panel_bg(self.screen, r)
        self._vline(self.screen, r.left, r.top, r.bottom, alpha=80)

        y = r.top + 4
        tasks = self.tasks
        total = len(tasks)
        done  = sum(1 for t in tasks if t["done"])

        self._text(self.screen, "OBJECTIVES", (r.left + 6, y),
                   C["green_dim"], self.font_sm)
        self._text(self.screen, f"{done}/{total}",
                   (r.right - 6, y), C["amber"], self.font_sm, anchor="topright")
        y += 14

        # Progress bar
        self._draw_progress_bar(r.left + 6, y, r.w - 12, 6,
                                done / max(total, 1), C["green"], C["cyan"])
        y += 14

        self._hline(self.screen, y, r.left, r.right, alpha=40)
        y += 4

        # Scrollable task list
        visible_h = r.bottom - y - 80
        line_h = 26
        max_visible = visible_h // line_h
        self.obj_scroll = min(self.obj_scroll, max(0, total - max_visible))

        for i, task in enumerate(tasks[self.obj_scroll:self.obj_scroll + max_visible]):
            if y + line_h > r.bottom - 80:
                break
            self._draw_objective(r, y, task)
            y += line_h

        # ── Day progress ──
        y = r.bottom - 76
        self._hline(self.screen, y, r.left, r.right, alpha=40)
        y += 4
        self._text(self.screen, "DAY PROGRESS", (r.left + 6, y),
                   C["green_dim"], self.font_sm)
        y += 12

        now = datetime.now()
        start_h, end_h = 7, 19
        elapsed = max(0, (now.hour - start_h) * 60 + now.minute)
        total_m = (end_h - start_h) * 60
        pct = min(1.0, elapsed / total_m)

        self._draw_progress_bar(r.left + 6, y, r.w - 12, 6,
                                pct, C["blue2"], C["cyan"])
        y += 12
        self._text(self.screen,
                   f"{int(pct*100)}%  ·  {now.strftime('%H:%M')}",
                   (r.left + 6, y), C["blue"], self.font_sm)

        # ── Next task callout ──
        y += 18
        next_task = next((t for t in tasks if not t["done"]), None)
        if next_task:
            self._text(self.screen, "NEXT:", (r.left + 6, y),
                       C["amber"], self.font_sm)
            self._text(self.screen, next_task["title"][:22],
                       (r.left + 6, y + 11), C["amber2"], self.font_sm)

    def _draw_objective(self, panel_r, y, task):
        x = panel_r.left + 6
        done   = task["done"]
        col    = C["green_dim"] if done else C["green"]
        ind    = C["green2"] if done else C["amber"]
        marker = "▣" if done else "▢"
        self._text(self.screen, marker, (x, y + 3), ind, self.font_sm)
        title = task["title"][:24]
        if done:
            # Strike-through approximation — dim + underscore
            self._text(self.screen, title, (x + 14, y + 3), C["green_dim"], self.font_sm)
        else:
            self._text(self.screen, title, (x + 14, y + 3), col, self.font_sm)
        if task.get("due"):
            self._text(self.screen, task["due"],
                       (x + 14, y + 14), _dim(C["green_dim"], 120), self.font_sm)

    # ── BOTTOM BAR ────────────────────────────────────────

    def _draw_bottom_bar(self):
        r = self._bot_rect
        pygame.draw.rect(self.screen, C["bg2"], r)
        self._hline(self.screen, r.top, alpha=80)

        tasks  = self.tasks
        done   = [t for t in tasks if t["done"]]
        active = [t for t in tasks if not t["done"]]

        sec_w = (self.W - 180) // 3
        sections = [
            ("↓ INCOMING", active[:2],  C["cyan"],      0),
            ("● ACTIVE",   active[2:4], C["amber"],     sec_w),
            ("✓ LANDED",   done[-2:],   C["green_dim"], sec_w * 2),
        ]

        for label, items, col, ox in sections:
            x = ox
            # Header
            self._text(self.screen, label, (x + 6, r.top + 3), col, self.font_sm)
            self._vline(self.screen, x + sec_w - 1, r.top, r.bottom, alpha=40)
            # Items
            for i, task in enumerate(items):
                iy = r.top + 16 + i * 17
                cs = ("BLK-" + task["title"][:6].upper().replace(" ",""))[:9]
                self._text(self.screen, cs, (x + 6, iy), col, self.font_sm)
                self._text(self.screen, task["title"][:18],
                           (x + 70, iy), C["green_dim"], self.font_sm)
                due = task.get("due","")
                if due:
                    self._text(self.screen, due, (x + sec_w - 70, iy),
                               _dim(col, 140), self.font_sm)

        # Compass (right side)
        self._draw_compass(self.W - 170, r.top + 4, 44)

        # AC count / info
        n = len(self.aircraft)
        info_x = self.W - 120
        self._text(self.screen, f"TRAFFIC",   (info_x, r.top + 4),  C["green_dim"], self.font_sm)
        self._text(self.screen, f"{n:02d} AC", (info_x, r.top + 15), C["cyan"],      self.font_md)
        ts = datetime.fromtimestamp(self.fetch_ts).strftime("%H:%M") if self.fetch_ts else "--:--"
        self._text(self.screen, f"UPD {ts}",  (info_x, r.top + 29), C["green_dim"], self.font_sm)
        self._text(self.screen, "[r] REFRESH",(info_x, r.top + 40), C["amber"],     self.font_sm)

    def _draw_compass(self, cx, top, size):
        cy = top + size // 2
        r  = size // 2 - 2
        # Ring
        s = pygame.Surface((size + 4, size + 4), pygame.SRCALPHA)
        pygame.draw.circle(s, (0,255,65,50), (size//2+2, size//2+2), r, 1)
        self.screen.blit(s, (cx - size//2 - 2, top))
        # Tick marks
        for i in range(36):
            a = math.radians(i * 10 - 90)
            inner = r - (5 if i % 9 == 0 else 2)
            x0 = cx + int(math.cos(a) * inner)
            y0 = cy + int(math.sin(a) * inner)
            x1 = cx + int(math.cos(a) * r)
            y1 = cy + int(math.sin(a) * r)
            col = C["green"] if i % 9 == 0 else _dim(C["green_dim"], 100)
            pygame.draw.line(self.screen, col, (x0, y0), (x1, y1), 1)
        # Cardinals
        for label, deg in [("N",0),("E",90),("S",180),("W",270)]:
            a   = math.radians(deg - 90)
            tx  = cx + int(math.cos(a) * (r - 10))
            ty  = cy + int(math.sin(a) * (r - 10))
            col = C["red"] if label == "N" else C["green"]
            self._text(self.screen, label, (tx, ty), col, self.font_sm, anchor="center")

    def _draw_progress_bar(self, x, y, w, h, pct, col_fill, col_tip):
        pygame.draw.rect(self.screen, C["green_dark"], (x, y, w, h))
        pygame.draw.rect(self.screen, _dim(C["green_dim"], 80), (x, y, w, h), 1)
        filled = int(w * pct)
        if filled > 0:
            pygame.draw.rect(self.screen, col_fill, (x, y, filled, h))
            pygame.draw.rect(self.screen, col_tip, (x + filled - 1, y, 2, h))


# ═══════════════════════════════════════════════════════════
#  COLOUR UTILITY
# ═══════════════════════════════════════════════════════════

def _dim(color, alpha=128):
    """Return an RGB tuple darkened by alpha factor (0-255)."""
    return tuple(int(c * alpha / 255) for c in color[:3])


# ═══════════════════════════════════════════════════════════
#  SHELL INTEGRATION — autoflight_ui.py wrapper
# ═══════════════════════════════════════════════════════════

class AutoflightUI:
    """
    Thin wrapper so shell.py can call:
        self.autoflight_ui.run()
    exactly like radar_ui, pulse_ui etc.
    """

    def __init__(self, vault, config):
        self.vault    = vault
        self.config   = config
        self.callsign = getattr(config, "callsign", "ADMIN-1")

    def run(self):
        vault_root = self.vault.root if hasattr(self.vault, "root") else Path.home() / "bloc"
        display = AutoflightDisplay(
            vault_root  = vault_root,
            config      = self.config,
            callsign    = self.callsign,
        )
        display.run()


# ═══════════════════════════════════════════════════════════
#  STANDALONE ENTRY POINT
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Run standalone with a dummy vault path for testing
    vault_root = Path.home() / "bloc"
    display = AutoflightDisplay(vault_root=vault_root)
    display.run()