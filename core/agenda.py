"""
agenda.py — BLOC AGENDA · DAILY TIME BLOCKING
───────────────────────────────────────────────
Time-block planner for the current day only.
Keyboard driven, no mouse. Matches shell.py patterns exactly.

Stored as:  ~/bloc/calendar/YYYY-MM-DD.md
Format:
    ## 09:00 → 10:30 | DEEP WORK
    > Build RADAR module
    - [ ] Draft README
    - [ ] Push to git

Commands (from shell menu, key 'a'):
    Shows today's blocks in HUD style.
    Sub-commands:
        a  — add new block
        e  — edit block (by number)
        d  — delete block
        c  — mark block complete
        n  — jump to now (highlight current)
        q  — back to shell

Voice intents handled by intent_parser additions:
    "block 2pm to 3pm for writing"
    "schedule 10am to 11am deep work"
    "what's my agenda"
    "next block"
"""

import re
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


# ═══════════════════════════════════════════════════════════
#  DATA MODEL
# ═══════════════════════════════════════════════════════════

class TimeBlock:
    """A single agenda block."""

    def __init__(self, start: str, end: str, label: str,
                 description: str = "", done: bool = False):
        self.start       = start        # "HH:MM"
        self.end         = end          # "HH:MM"
        self.label       = label.upper()
        self.description = description  # free text body
        self.done        = done

    @property
    def start_dt(self) -> datetime:
        h, m = map(int, self.start.split(":"))
        return datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)

    @property
    def end_dt(self) -> datetime:
        h, m = map(int, self.end.split(":"))
        return datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)

    @property
    def duration_min(self) -> int:
        delta = self.end_dt - self.start_dt
        return max(0, int(delta.total_seconds() / 60))

    @property
    def is_active(self) -> bool:
        now = datetime.now()
        return self.start_dt <= now < self.end_dt

    @property
    def is_past(self) -> bool:
        return datetime.now() >= self.end_dt

    @property
    def is_upcoming(self) -> bool:
        return datetime.now() < self.start_dt

    @property
    def status(self) -> str:
        if self.done:        return "LANDED"
        if self.is_active:   return "IN SECTOR"
        if self.is_past:     return "ELAPSED"
        if self.is_upcoming: return "QUEUED"
        return "UNKNOWN"

    @property
    def progress(self) -> float:
        """0.0 → 1.0 completion of active block."""
        if not self.is_active:
            return 1.0 if self.is_past else 0.0
        elapsed = (datetime.now() - self.start_dt).total_seconds()
        total   = max(1, self.duration_min * 60)
        return min(1.0, elapsed / total)

    @property
    def remaining_str(self) -> str:
        if not self.is_active:
            return ""
        rem = int((self.end_dt - datetime.now()).total_seconds())
        h, s = divmod(rem, 3600)
        m, s = divmod(s, 60)
        if h:
            return f"{h}H {m:02d}M"
        return f"{m:02d}M {s:02d}S"

    def to_md(self) -> str:
        done_mark = " ✓" if self.done else ""
        lines = [f"## {self.start} → {self.end} | {self.label}{done_mark}"]
        if self.description:
            for line in self.description.strip().splitlines():
                lines.append(line)
        lines.append("")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  PARSER — reads/writes the .md file
# ═══════════════════════════════════════════════════════════

class AgendaFile:
    """
    Reads and writes ~/bloc/calendar/YYYY-MM-DD.md
    Keeps blocks sorted by start time.
    """

    HEADER_RE = re.compile(
        r"^## (\d{2}:\d{2}) → (\d{2}:\d{2}) \| (.+)$"
    )

    def __init__(self, calendar_dir: Path, date: datetime = None):
        self.date         = (date or datetime.now()).date()
        self.calendar_dir = calendar_dir
        self.calendar_dir.mkdir(parents=True, exist_ok=True)
        self.filepath     = calendar_dir / f"{self.date}.md"
        self.blocks: list[TimeBlock] = []
        self.load()

    def load(self):
        """Parse blocks from disk."""
        self.blocks = []
        if not self.filepath.exists():
            return
        current_block  = None
        desc_lines     = []
        for raw_line in self.filepath.read_text(encoding="utf-8").splitlines():
            line  = raw_line.rstrip()
            match = self.HEADER_RE.match(line)
            if match:
                if current_block is not None:
                    current_block.description = "\n".join(desc_lines).strip()
                    self.blocks.append(current_block)
                    desc_lines = []
                start, end, label = match.groups()
                done  = label.endswith(" ✓")
                label = label.removesuffix(" ✓").strip()
                current_block = TimeBlock(start, end, label, done=done)
            elif current_block is not None:
                desc_lines.append(line)
        if current_block is not None:
            current_block.description = "\n".join(desc_lines).strip()
            self.blocks.append(current_block)

        self._sort()

    def save(self):
        """Write all blocks to disk."""
        self._sort()
        header = f"# AGENDA · {self.date.strftime('%A %d %B %Y').upper()}\n\n"
        body   = "\n".join(b.to_md() for b in self.blocks)
        self.filepath.write_text(header + body, encoding="utf-8")

    def add(self, block: TimeBlock):
        self.blocks.append(block)
        self._sort()
        self.save()

    def delete(self, index: int) -> bool:
        if 0 <= index < len(self.blocks):
            self.blocks.pop(index)
            self.save()
            return True
        return False

    def complete(self, index: int) -> bool:
        if 0 <= index < len(self.blocks):
            self.blocks[index].done = True
            self.save()
            return True
        return False

    def _sort(self):
        self.blocks.sort(key=lambda b: b.start)

    @property
    def active_block(self) -> TimeBlock | None:
        for b in self.blocks:
            if b.is_active:
                return b
        return None

    @property
    def next_block(self) -> TimeBlock | None:
        for b in self.blocks:
            if b.is_upcoming:
                return b
        return None

    @property
    def stats(self) -> dict:
        total   = len(self.blocks)
        done    = sum(1 for b in self.blocks if b.done)
        past    = sum(1 for b in self.blocks if b.is_past)
        active  = 1 if any(b.is_active for b in self.blocks) else 0
        upcoming= total - past - active
        return {
            "total":    total,
            "done":     done,
            "past":     past,
            "active":   active,
            "upcoming": upcoming,
        }


# ═══════════════════════════════════════════════════════════
#  TIME PARSING HELPERS
# ═══════════════════════════════════════════════════════════

def _parse_time(raw: str) -> str | None:
    """
    Parse natural time strings → "HH:MM"
    Accepts: "9am", "14:30", "2:30pm", "1430", "09:00"
    Returns None if unparseable.
    """
    raw = raw.strip().lower()

    # HH:MM or H:MM
    m = re.match(r"^(\d{1,2}):(\d{2})(?:am|pm)?$", raw)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if "pm" in raw and h < 12: h += 12
        if "am" in raw and h == 12: h = 0
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return f"{h:02d}:{mn:02d}"

    # HHMM
    m = re.match(r"^(\d{4})$", raw)
    if m:
        h, mn = int(raw[:2]), int(raw[2:])
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return f"{h:02d}:{mn:02d}"

    # Ham / Hpm
    m = re.match(r"^(\d{1,2})(am|pm)$", raw)
    if m:
        h = int(m.group(1))
        if m.group(2) == "pm" and h < 12: h += 12
        if m.group(2) == "am" and h == 12: h = 0
        if 0 <= h <= 23:
            return f"{h:02d}:00"

    return None


def parse_block_from_voice(text: str) -> dict | None:
    """
    Parse a voice/text string into block components.
    Handles:
      "block 2pm to 3pm for writing"
      "schedule 10am to 11:30am deep work"
      "add block 09:00 to 10:30 radar module"
    Returns dict or None.
    """
    text = text.lower().strip()
    text = re.sub(r"^(block|schedule|add block|plan)\s*", "", text)

    # Try: <time> to <time> [for|label] <label>
    m = re.search(
        r"(\d{1,2}(?::\d{2})?(?:am|pm)?)"
        r"\s+(?:to|until|till|-)\s+"
        r"(\d{1,2}(?::\d{2})?(?:am|pm)?)"
        r"(?:\s+(?:for|label|:)?\s+(.+))?",
        text
    )
    if not m:
        return None

    start_raw, end_raw, label_raw = m.group(1), m.group(2), m.group(3)
    start = _parse_time(start_raw)
    end   = _parse_time(end_raw)
    if not start or not end:
        return None

    label = (label_raw or "BLOCK").strip().upper()
    return {"start": start, "end": end, "label": label}


# ═══════════════════════════════════════════════════════════
#  AGENDA UI — integrates with shell.py environment/chars
# ═══════════════════════════════════════════════════════════

BAR_WIDTH   = 20
STATUS_COL  = 52     # dot padding column
AGENDA_COL  = 72     # full line width


def _pad_dots(left: str, right: str, width: int = STATUS_COL) -> str:
    dots = "·" * max(1, width - len(left) - len(right) - 4)
    return f"    {left} {dots} {right}"


class AgendaUI:
    """
    Agenda screen — plugs into shell.py exactly like PulseUI, RadarUI.
    Call: self.agenda_ui.run()
    """

    def __init__(self, calendar_dir: Path, env, config=None):
        self.calendar_dir = calendar_dir
        self.env          = env
        self.config       = config
        self.agenda       = AgendaFile(calendar_dir)

    def _get_key(self):
        if os.name == "nt":
            import msvcrt
            return msvcrt.getwch()
        else:
            import tty, termios
            fd  = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                return sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

    # ── MAIN LOOP ─────────────────────────────────────────

    def run(self):
        while True:
            self._draw()
            key = self._get_key().lower()
            if key == "q":
                break
            elif key == "a":
                self._add_block_interactive()
            elif key == "d":
                self._delete_block_interactive()
            elif key == "c":
                self._complete_block_interactive()
            elif key == "e":
                self._edit_block_interactive()
            elif key == "r":
                self.agenda.load()   # manual reload
                self._status("AGENDA REFRESHED FROM DISK")

    # ── DRAW ──────────────────────────────────────────────

    def _draw(self):
        env = self.env
        env.clear()
        self._header()
        self._draw_blocks()
        self._draw_footer()

    def _header(self):
        env   = self.env
        c     = env.char
        now   = datetime.now()
        stats = self.agenda.stats

        env.accent(
            f"    {c('corner_tl')} AGENDA"
            f"    {now.strftime('%a %d %b %Y').upper()}"
            f"    BLOCKS [{stats['total']:02d}]"
            f"    ACTIVE [{stats['active']}]"
            f"    QUEUED [{stats['upcoming']}]"
        )
        env.separator("double")
        print()

    def _draw_blocks(self):
        env    = self.env
        blocks = self.agenda.blocks

        if not blocks:
            env.dim(f"    {env.char('indicator_off')} NO FLIGHT PLAN FOR TODAY")
            env.dim(f"    ◈ PRESS [a] TO ADD FIRST BLOCK")
            print()
            return

        # Day timeline bar
        self._draw_day_bar()
        print()

        for i, block in enumerate(blocks, 1):
            self._draw_block_row(i, block)
            print()

    def _draw_day_bar(self):
        """Compact timeline: 07:00 ████░░░░░░░░ 19:00"""
        env      = self.env
        now      = datetime.now()
        start_h, end_h = 7, 19
        total    = (end_h - start_h) * 60
        elapsed  = max(0, (now.hour - start_h) * 60 + now.minute)
        pct      = min(1.0, elapsed / total)

        bar      = env.bar(pct, width=BAR_WIDTH)
        time_str = now.strftime("%H:%M")
        label    = f"07:00  [{bar}]  19:00"
        pct_str  = f"{int(pct*100):02d}% · {time_str}"
        env.dim(_pad_dots(label, pct_str))

    def _draw_block_row(self, i: int, block: TimeBlock):
        env    = self.env
        c      = env.char
        status = block.status
        dur    = f"{block.duration_min}M"

        # ── select colour style per status ────────────────
        if block.done:
            style    = "dim"
            marker   = c("bullet_done")
            tag      = "✓ LANDED"
        elif block.is_active:
            style    = "accent"   # amber
            marker   = c("bullet_active")
            tag      = f"● {block.remaining_str}"
        elif block.is_past:
            style    = "dim"
            marker   = c("bullet")
            tag      = "ELAPSED"
        else:
            style    = "primary"
            marker   = c("bullet")
            tag      = "QUEUED"

        # ── row 1: index · marker · time range · label ────
        time_range = f"{block.start} → {block.end}"
        left       = f"{i:02d}  {marker}  {time_range}  {block.label}"
        env.p(_pad_dots(left, f"[{dur}] {tag}"), style)

        # ── row 2: progress bar if active ─────────────────
        if block.is_active:
            bar = env.bar(block.progress, width=BAR_WIDTH)
            env.accent(f"         [{bar}]  {int(block.progress*100):02d}%")

        # ── row 3: description preview ────────────────────
        if block.description:
            for desc_line in block.description.splitlines()[:2]:
                if desc_line.strip():
                    env.dim(f"         {desc_line.strip()[:60]}")

        env.separator("dot")

    def _draw_footer(self):
        env = self.env
        env.separator("double")
        env.accent(
            f"    [a] ADD  ·  [e] EDIT  ·  [c] COMPLETE  ·  "
            f"[d] DELETE  ·  [r] RELOAD  ·  [q] BACK"
        )
        env.separator("double")
        env.accent("    CMD ▶ ", end="")

    # ── ADD BLOCK ─────────────────────────────────────────

    def _add_block_interactive(self):
        env = self.env
        env.clear()
        env.accent(f"    {env.char('corner_tl')} AGENDA · ADD BLOCK\n")
        env.separator()
        print()

        # Start time
        env.dim("    ◈ START TIME ·········· (e.g. 09:00 or 9am): ", end="")
        raw_start = input().strip()
        start = _parse_time(raw_start)
        if not start:
            env.alert(f"    ◈ FAULT ················ INVALID TIME FORMAT")
            self._pause()
            return

        # End time
        env.dim("    ◈ END TIME ············ (e.g. 10:30 or 10am): ", end="")
        raw_end = input().strip()
        end = _parse_time(raw_end)
        if not end:
            env.alert(f"    ◈ FAULT ················ INVALID TIME FORMAT")
            self._pause()
            return

        # Label
        env.dim("    ◈ BLOCK LABEL ········· (e.g. DEEP WORK): ", end="")
        label = input().strip()
        if not label:
            label = "BLOCK"

        # Optional description
        env.dim("    ◈ DESCRIPTION ·········· (blank to skip): ", end="")
        desc = input().strip()

        block = TimeBlock(start, end, label, description=desc)
        self.agenda.add(block)

        print()
        env.accent(
            f"    ◈ BLOCK LOGGED ········ "
            f"{start} → {end}  {label.upper()}"
        )
        self._pause()

    # ── VOICE ADD (called by voice_handler) ───────────────

    def add_from_voice(self, text: str) -> str:
        """
        Parse voice string and add block if valid.
        Returns status message for shell confirmation line.
        """
        parsed = parse_block_from_voice(text)
        if not parsed:
            return "INTENT UNRESOLVED · BLOCK NOT ADDED"
        block = TimeBlock(parsed["start"], parsed["end"], parsed["label"])
        self.agenda.add(block)
        return f"BLOCK LOGGED · {parsed['start']} → {parsed['end']} · {parsed['label']}"

    # ── COMPLETE ──────────────────────────────────────────

    def _complete_block_interactive(self):
        env = self.env
        env.clear()
        env.accent(f"    {env.char('corner_tl')} AGENDA · COMPLETE BLOCK\n")
        env.separator()
        print()
        for i, b in enumerate(self.agenda.blocks, 1):
            env.primary(f"    {env.char('bullet')}  {i:02d}  {b.start} → {b.end}  {b.label}")
        print()
        env.accent("    ◈ BLOCK NUMBER ········ ", end="")
        try:
            idx = int(input().strip()) - 1
            if self.agenda.complete(idx):
                env.accent(f"    ◈ BLOCK ················ TOUCHDOWN ✓")
            else:
                env.alert(f"    ◈ FAULT ················ INVALID NUMBER")
        except ValueError:
            env.alert(f"    ◈ FAULT ················ INVALID INPUT")
        self._pause()

    # ── DELETE ────────────────────────────────────────────

    def _delete_block_interactive(self):
        env = self.env
        env.clear()
        env.accent(f"    {env.char('corner_tl')} AGENDA · DELETE BLOCK\n")
        env.separator()
        print()
        for i, b in enumerate(self.agenda.blocks, 1):
            env.primary(f"    {env.char('bullet')}  {i:02d}  {b.start} → {b.end}  {b.label}")
        print()
        env.accent("    ◈ BLOCK NUMBER ········ ", end="")
        try:
            idx = int(input().strip()) - 1
            env.alert("    ◈ CAUTION ·············· CONFIRM DELETE [y/n]: ", end="")
            if input().strip().lower() == "y":
                if self.agenda.delete(idx):
                    env.accent(f"    ◈ BLOCK ················ SCRUBBED")
                else:
                    env.alert(f"    ◈ FAULT ················ INVALID NUMBER")
            else:
                env.dim(f"    ◈ DELETION ············· ABORTED")
        except ValueError:
            env.alert(f"    ◈ FAULT ················ INVALID INPUT")
        self._pause()

    # ── EDIT ──────────────────────────────────────────────

    def _edit_block_interactive(self):
        env = self.env
        env.clear()
        env.accent(f"    {env.char('corner_tl')} AGENDA · EDIT BLOCK\n")
        env.separator()
        print()
        for i, b in enumerate(self.agenda.blocks, 1):
            env.primary(f"    {env.char('bullet')}  {i:02d}  {b.start} → {b.end}  {b.label}")
        print()
        env.accent("    ◈ BLOCK NUMBER ········ ", end="")
        try:
            idx = int(input().strip()) - 1
            if not (0 <= idx < len(self.agenda.blocks)):
                env.alert(f"    ◈ FAULT ················ INVALID NUMBER")
                self._pause()
                return

            block = self.agenda.blocks[idx]
            print()
            env.dim(f"    ◈ LEAVE BLANK TO KEEP CURRENT VALUE")
            print()

            env.dim(f"    ◈ START [{block.start}] ···· ", end="")
            raw = input().strip()
            if raw:
                t = _parse_time(raw)
                if t: block.start = t

            env.dim(f"    ◈ END   [{block.end}] ···· ", end="")
            raw = input().strip()
            if raw:
                t = _parse_time(raw)
                if t: block.end = t

            env.dim(f"    ◈ LABEL [{block.label}] ···· ", end="")
            raw = input().strip()
            if raw: block.label = raw.upper()

            self.agenda.save()
            env.accent(f"\n    ◈ BLOCK ················ UPDATED")
        except ValueError:
            env.alert(f"    ◈ FAULT ················ INVALID INPUT")
        self._pause()

    # ── HELPERS ───────────────────────────────────────────

    def _status(self, msg: str):
        self.env.accent(f"    ◈ AGENDA ··············· {msg}")

    def _pause(self):
        print()
        self.env.dim(f"    ◈ STANDING BY ·········· PRESS ANY KEY")
        self._get_key()

    # ── QUICK STATUS (for shell header sparkline) ─────────

    def status_line(self) -> str:
        """One-line summary for shell header."""
        active = self.agenda.active_block
        nxt    = self.agenda.next_block
        if active:
            return f"IN SECTOR · {active.label} · {active.remaining_str}"
        if nxt:
            return f"NEXT · {nxt.start} · {nxt.label}"
        stats = self.agenda.stats
        return f"BLOCKS {stats['done']}/{stats['total']} CLEARED"


# ═══════════════════════════════════════════════════════════
#  INTENT PARSER ADDITIONS
#  Add these patterns to IntentParser.patterns in intent_parser.py
# ═══════════════════════════════════════════════════════════

AGENDA_INTENT_PATTERNS = {
    "new_block": [
        r"(?:block|schedule|add block|plan)\s+(.+)",
        r"(?:set aside|reserve|allocate)\s+(.+)",
    ],
    "show_agenda": [
        r"(?:show|what'?s|read|open)\s+(?:my\s+)?agenda",
        r"(?:show|list)\s+(?:my\s+)?(?:schedule|time blocks|blocks)",
        r"what(?:'s|\s+is)\s+(?:on\s+)?(?:my\s+)?(?:schedule|agenda)\??",
        r"next block",
        r"what'?s next",
        r"what am i doing",
    ],
}

# To integrate: in intent_parser.py, add to __init__:
#   from core.agenda import AGENDA_INTENT_PATTERNS
#   self.patterns.update(AGENDA_INTENT_PATTERNS)


# ═══════════════════════════════════════════════════════════
#  STANDALONE TEST
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Quick test without full shell boot
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    # Mock env for testing
    class _MockEnv:
        def accent(self, t, end="\n"):   print(t, end=end)
        def primary(self, t, end="\n"):  print(t, end=end)
        def dim(self, t, end="\n"):      print(t, end=end)
        def alert(self, t, end="\n"):    print(t, end=end)
        def critical(self, t, end="\n"): print(t, end=end)
        def p(self, t, style="primary", end="\n"): print(t, end=end)
        def separator(self, style="single"):
            print("────────────────────────────────────────")
        def bar(self, v, width=20):
            f = round(v * width)
            return "█" * f + "░" * (width - f)
        def char(self, name):
            chars = {
                "corner_tl": "◈", "bullet": "▢", "bullet_done": "▣",
                "bullet_active": "▶", "indicator_off": "○", "indicator": "●",
            }
            return chars.get(name, "·")
        def clear(self): os.system("cls" if os.name == "nt" else "clear")

    cal_dir = Path.home() / "bloc" / "calendar"
    env     = _MockEnv()
    ui      = AgendaUI(cal_dir, env)

    # Seed some test blocks if empty
    if not ui.agenda.blocks:
        ui.agenda.add(TimeBlock("07:30", "08:00", "MORNING BRIEF",
                                "Review yesterday's flight log"))
        ui.agenda.add(TimeBlock("09:00", "10:30", "DEEP WORK",
                                "Build RADAR module\n- Draft README\n- Push to git"))
        ui.agenda.add(TimeBlock("10:30", "11:00", "COMMS",
                                "Reply to messages"))
        ui.agenda.add(TimeBlock("14:00", "15:30", "DESIGN REVIEW",
                                "BLOC OS interface pass"))
        print("TEST BLOCKS SEEDED")

    ui.run()