import os
import time
from ui.environment import Environment
from core.pulse import Pulse

if os.name == 'nt':
    import msvcrt
    def get_key_nowait():
        if msvcrt.kbhit():
            return msvcrt.getwch()
        return None
else:
    import sys, tty, termios, select
    def get_key_nowait():
        if select.select([sys.stdin], [], [], 0)[0]:
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                return sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return None


V = {
    "saved":   "LOGGED",
    "standby": "STANDING BY",
    "ended":   "SESSION ENDED · LOG SAVED",
}


class PulseUI:
    """Terminal UI for PULSE focus timer."""

    def __init__(self, pulse: Pulse, env: Environment):
        self.pulse = pulse
        self.env   = env

    def clear(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def _draw(self):
        self.clear()
        session = self.pulse.current_session
        c       = self.env.char

        # ── header with breadcrumb ────────────────────────
        self.env.accent(
            f"    {self.env.char('corner_tl')} BLOC OS"
            f"    [ PULSE · FOCUS TIMER ]"
            f"    FLT [{self.pulse.total_flight_time}]"
        )
        self.env.separator("double")
        self.env.dim(
            f"    SESSION "
            f"{self.pulse.completed_study + 1} / {self.pulse.total_study}"
            f"                          [ PULSE · TIMER ]"
        )
        self.env.separator()
        print()

        if not session:
            self.env.dim("    ◈ ALL SESSIONS COMPLETE")
            return

        # ── session type ──────────────────────────────────
        type_label = {
            "study":      "STUDY",
            "break":      "BREAK",
            "long_break": "LONG BREAK",
        }.get(session.type, session.type.upper())

        self.env.accent(f"    {type_label}")
        print()

        # ── timer ─────────────────────────────────────────
        self.env.primary(
            f"    {c('arrow_dn')} {session.remaining_str} REMAINING"
        )
        print()

        # ── progress bar ──────────────────────────────────
        bar = self.env.bar(session.progress, width=36)
        pct = int(session.progress * 100)
        self.env.primary(f"    {bar}  {pct}%")
        print()

        # ── session plan overview ─────────────────────────
        self.env.separator("dot")
        self.env.dim("    SESSION LOG")
        for s in self.pulse.sessions:
            if s.completed:
                marker = c("bullet_done")
                style  = "dim"
            elif s.index == self.pulse.current_session.index:
                marker = c("bullet_active")
                style  = "accent"
            else:
                marker = c("bullet")
                style  = "dim"
            dur = f"{s.duration // 60}m"
            self.env.p(f"    {marker}  {s.type.upper():<12} {dur}", style)
        print()

        # ── status ────────────────────────────────────────
        self.env.separator()
        if self.pulse.paused:
            self.env.alert("    ◈ PAUSED · TIMER HOLDING")
        elif self.pulse.active:
            self.env.primary(f"    {c('indicator')} ACTIVE · TIMER RUNNING")
        else:
            self.env.dim(f"    {c('indicator_off')} {V['standby']}")

        print()
        self.env.separator("double")
        self.env.dim(
            "    s START  ·  r RESUME  ·  x SKIP  ·  e END  ·  q BACK"
        )
        print()
        self.env.accent(f"    CMD {c('arrow_rt')} ", end="")
        print("", end="", flush=True)

    def run(self):
        """Main pulse UI loop — live updating timer."""
        last_second = -1

        while True:
            session        = self.pulse.current_session
            current_second = session.remaining if session else 0

            if current_second != last_second:
                self._draw()
                last_second = current_second

            key = get_key_nowait()
            if key:
                key = key.lower()
                if key == 'q':
                    break
                elif key == 's':
                    self.pulse.start()
                elif key == 'r':
                    self.pulse.resume()
                elif key == 'x':
                    self.pulse.skip()
                elif key == 'e':
                    self.pulse.end_all()
                    self._draw()
                    self.env.accent(f"\n    ◈ {V['ended']}")
                    time.sleep(1.5)
                    break

            time.sleep(0.05)