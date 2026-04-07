import time
import math
import threading
import urllib.request
import json

# ─── LONDON TMA BOUNDING BOX ──────────────────────────────
# Covers roughly the London Terminal Manoeuvring Area
LONDON_TMA = {
    "lat_min": 51.0,
    "lat_max": 52.0,
    "lon_min": -1.0,
    "lon_max":  0.6,
}

# OpenSky REST endpoint — no auth required, 10s resolution
OPENSKY_URL = (
    "https://opensky-network.org/api/states/all"
    "?lamin={lat_min}&lamax={lat_max}&lomin={lon_min}&lomax={lon_max}"
)

REFRESH_INTERVAL = 15  # seconds between API polls


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two lat/lon points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Bearing in degrees from point 1 → point 2."""
    dlon = math.radians(lon2 - lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2)
    y = (math.cos(lat1) * math.sin(lat2)
         - math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


class Aircraft:
    """Parsed state vector from OpenSky."""

    __slots__ = (
        "icao", "callsign", "lat", "lon",
        "altitude_m", "speed_ms", "track_deg",
        "on_ground", "last_seen",
    )

    def __init__(self, state):
        self.icao      = (state[0] or "??????").upper()
        self.callsign  = (state[1] or "--------").strip().upper() or "--------"
        self.lat       = state[6]   # degrees
        self.lon       = state[5]   # degrees
        self.altitude_m = state[7] or 0   # baro altitude metres
        self.speed_ms  = state[9] or 0    # ground speed m/s
        self.track_deg = state[10] or 0   # track angle degrees
        self.on_ground = bool(state[8])
        self.last_seen = state[4] or 0

    @property
    def altitude_ft(self):
        return int(self.altitude_m * 3.281)

    @property
    def speed_kt(self):
        return int(self.speed_ms * 1.944)

    @property
    def fl(self):
        """Flight level string e.g. FL120, or GND."""
        if self.on_ground:
            return "GND"
        fl = self.altitude_ft // 100
        return f"FL{fl:03d}"

    def direction_arrow(self):
        """8-point compass arrow matching HUD_CHARS aircraft list."""
        arrows = ["▲", "↗", "▶", "↘", "▼", "↙", "◀", "↖"]
        idx = int((self.track_deg + 22.5) / 45) % 8
        return arrows[idx]


class Radar:
    """
    Background poller for OpenSky ADS-B data over London TMA.
    Thread-safe — UI reads .aircraft, .last_updated, .error.
    """

    def __init__(self, config, bbox=None):
        self.config = config
        self.bbox = bbox or LONDON_TMA
        self.aircraft: list[Aircraft] = []
        self.last_updated: float = 0
        self.error: str = ""
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    # ─── public api ───────────────────────────────────────

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()

    def snapshot(self):
        """Return a thread-safe copy of current aircraft list."""
        with self._lock:
            return list(self.aircraft), self.last_updated, self.error

    def fetch_once(self):
        """Blocking single fetch — use from UI for manual refresh."""
        self._fetch()

    # ─── relative geometry helpers ────────────────────────

    def relative_to_centre(self, ac: Aircraft):
        """
        Returns (distance_km, bearing_deg) from centre of bbox
        to the aircraft.
        """
        clat = (self.bbox["lat_min"] + self.bbox["lat_max"]) / 2
        clon = (self.bbox["lon_min"] + self.bbox["lon_max"]) / 2
        dist = haversine_km(clat, clon, ac.lat, ac.lon)
        bear = bearing_deg(clat, clon, ac.lat, ac.lon)
        return dist, bear

    def to_radar_xy(self, ac: Aircraft, radius: int):
        """
        Map aircraft lat/lon onto a circular radar scope.
        radius = pixel/char radius of the scope.
        Returns (x, y) integers, or None if outside scope.
        """
        clat = (self.bbox["lat_min"] + self.bbox["lat_max"]) / 2
        clon = (self.bbox["lon_min"] + self.bbox["lon_max"]) / 2

        lat_range = self.bbox["lat_max"] - self.bbox["lat_min"]
        lon_range = self.bbox["lon_max"] - self.bbox["lon_min"]

        # Normalise to [-1, 1]
        ny = (ac.lat - clat) / (lat_range / 2)
        nx = (ac.lon - clon) / (lon_range / 2)

        # Reject if outside unit circle
        if nx ** 2 + ny ** 2 > 1.0:
            return None

        x = int(nx * radius)
        y = int(-ny * radius)  # screen y increases downward
        return x, y

    # ─── internals ────────────────────────────────────────

    def _poll_loop(self):
        self._fetch()
        while not self._stop.wait(REFRESH_INTERVAL):
            self._fetch()

    def _fetch(self):
        url = OPENSKY_URL.format(**self.bbox)
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BLOC-OS/0.1"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            states = data.get("states") or []
            parsed = []
            for s in states:
                try:
                    ac = Aircraft(s)
                    # Drop entries with no position
                    if ac.lat is not None and ac.lon is not None:
                        parsed.append(ac)
                except Exception:
                    pass

            # Sort by altitude descending (high traffic first)
            parsed.sort(key=lambda a: a.altitude_m, reverse=True)

            with self._lock:
                self.aircraft = parsed
                self.last_updated = time.time()
                self.error = ""

        except Exception as e:
            with self._lock:
                self.error = str(e)[:60]