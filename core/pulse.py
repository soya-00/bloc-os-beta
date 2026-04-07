import time
import threading
from datetime import datetime
from pathlib import Path


class PulseSession:
    """Represents a single focus or break block."""
    def __init__(self, session_type: str, duration_minutes: int, index: int):
        self.type = session_type        # "study" | "break" | "long_break"
        self.duration = duration_minutes * 60  # convert to seconds
        self.index = index
        self.started_at = None
        self.ended_at = None
        self.completed = False
        self.interrupted = False

    @property
    def elapsed(self) -> int:
        if not self.started_at:
            return 0
        end = self.ended_at or datetime.now()
        return int((end - self.started_at).total_seconds())

    @property
    def remaining(self) -> int:
        return max(0, self.duration - self.elapsed)

    @property
    def progress(self) -> float:
        if self.duration == 0:
            return 0.0
        return min(1.0, self.elapsed / self.duration)

    @property
    def remaining_str(self) -> str:
        mins = self.remaining // 60
        secs = self.remaining % 60
        return f"{mins:02d}:{secs:02d}"

    @property
    def elapsed_str(self) -> str:
        mins = self.elapsed // 60
        secs = self.elapsed % 60
        return f"{mins:02d}:{secs:02d}"


class Pulse:
    """
    BLOC focus session manager.
    Handles pomodoro, custom, and flow modes.
    Logs all sessions to ~/bloc/sessions/
    """

    def __init__(self, config, sessions_dir: Path):
        self.config = config
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        # Session state
        self.sessions = []
        self.current_index = 0
        self.active = False
        self.paused = False
        self._timer_thread = None
        self._stop_event = threading.Event()
        self._tick_callback = None  # called every second with current session
        self._complete_callback = None  # called when session completes

        self._build_session_plan()

    # ─── SESSION PLAN ─────────────────────────────────────

    def _build_session_plan(self):
        """Build the sequence of study/break sessions."""
        mode = self.config.get("pulse", "mode", "pomodoro")
        work = self.config.get("pulse", "work_duration", 25)
        short_break = self.config.get("pulse", "break_duration", 5)
        long_break = self.config.get("pulse", "long_break", 15)
        cycles = self.config.get("pulse", "sessions_before_long", 4)

        self.sessions = []
        index = 1

        if mode == "pomodoro":
            # 4 cycles: study, break, study, break... then long break
            for cycle in range(cycles):
                self.sessions.append(
                    PulseSession("study", work, index)
                )
                index += 1
                if cycle < cycles - 1:
                    self.sessions.append(
                        PulseSession("break", short_break, index)
                    )
                else:
                    self.sessions.append(
                        PulseSession("long_break", long_break, index)
                    )
                index += 1

        elif mode == "custom":
            for _ in range(cycles):
                self.sessions.append(PulseSession("study", work, index))
                index += 1
                self.sessions.append(PulseSession("break", short_break, index))
                index += 1

        elif mode == "flow":
            # Single long session, no break scheduled
            self.sessions.append(PulseSession("study", work * 4, index))

        self.current_index = 0

    # ─── CONTROLS ─────────────────────────────────────────

    def start(self):
        """Start or resume the current session."""
        if self.active and not self.paused:
            return

        session = self.current_session
        if not session:
            return

        if not session.started_at:
            session.started_at = datetime.now()

        self.active = True
        self.paused = False
        self._stop_event.clear()
        self._timer_thread = threading.Thread(
            target=self._run_timer,
            daemon=True
        )
        self._timer_thread.start()

    def pause(self):
        """Pause the current session."""
        if self.active and not self.paused:
            self.paused = True

    def resume(self):
        """Resume a paused session."""
        if self.paused:
            self.paused = False
            
    def skip(self):
        """Skip current session and move to next."""
        session = self.current_session
        if session:
            session.interrupted = True
            session.ended_at = datetime.now()
        self._stop_event.set()
        self.active = False
        self.paused = False
        self._advance()

    def reset(self):
        """Reset entire session plan."""
        self._stop_event.set()
        self.active = False
        self.paused = False
        self._build_session_plan()

    def end_all(self):
        """End session and save log."""
        self._stop_event.set()
        self.active = False
        self.paused = False
        session = self.current_session
        if session:
            session.ended_at = datetime.now()
        self._save_log()

    # ─── TIMER THREAD ─────────────────────────────────────

    def _run_timer(self):
        """Background thread — ticks every second."""
        while not self._stop_event.is_set():
            if self.paused:
                time.sleep(0.1)
                continue

            session = self.current_session
            if not session:
                break

            if session.remaining <= 0:
                session.completed = True
                session.ended_at = datetime.now()
                self.active = False
                if self._complete_callback:
                    self._complete_callback(session)
                self._advance()
                break

            time.sleep(1)
            
    def _advance(self):
        """Move to next session in plan."""
        if self.current_index < len(self.sessions) - 1:
            self.current_index += 1
        else:
            # All sessions done — save log and rebuild
            self._save_log()
            self._build_session_plan()

    # ─── STATE ────────────────────────────────────────────

    @property
    def current_session(self) -> PulseSession:
        if 0 <= self.current_index < len(self.sessions):
            return self.sessions[self.current_index]
        return None

    @property
    def study_sessions(self) -> list:
        return [s for s in self.sessions if s.type == "study"]

    @property
    def completed_study(self) -> int:
        return len([s for s in self.study_sessions if s.completed])

    @property
    def total_study(self) -> int:
        return len(self.study_sessions)

    @property
    def total_flight_time(self) -> str:
        """Total completed study time as HH:MM."""
        total_secs = sum(
            s.elapsed for s in self.sessions
            if s.type == "study" and s.completed
        )
        hours = total_secs // 3600
        mins = (total_secs % 3600) // 60
        return f"{hours:02d}H {mins:02d}M"

    def status_line(self) -> str:
        """Single line status for dashboard/status bar."""
        session = self.current_session
        if not session:
            return "NO ACTIVE SESSION"
        if not self.active and not self.paused:
            return f"READY  {session.type.upper()}  {session.remaining_str}"
        if self.paused:
            return f"PAUSED  {session.type.upper()}  {session.remaining_str}"
        return (
            f"{session.type.upper()}"
            f"  {session.remaining_str}"
            f"  SESSION {self.completed_study + 1}/{self.total_study}"
        )

    # ─── LOGGING ──────────────────────────────────────────

    def _save_log(self):
        """Save session log to ~/bloc/sessions/YYYY-MM-DD.md"""
        date = datetime.now().strftime("%Y-%m-%d")
        filepath = self.sessions_dir / f"{date}.md"

        completed = [s for s in self.sessions if s.started_at]
        if not completed:
            return

        total_focus = sum(
            s.elapsed for s in completed if s.type == "study"
        )
        total_break = sum(
            s.elapsed for s in completed if s.type != "study"
        )
        study_done = len([s for s in completed
                         if s.type == "study" and s.completed])
        study_total = len(self.study_sessions)

        lines = [
            f"# PULSE LOG · {date}\n",
            f"| Time | Type | Duration | Status |",
            f"|------|------|----------|--------|",
        ]

        for s in completed:
            if not s.started_at:
                continue
            t = s.started_at.strftime("%H:%M")
            dur = f"{s.elapsed // 60}:{s.elapsed % 60:02d}"
            status = "✅" if s.completed else "❌ interrupted"
            lines.append(f"| {t} | {s.type.upper()} | {dur} | {status} |")

        lines += [
            f"\n## SUMMARY",
            f"- Sessions completed: {study_done} / {study_total}",
            f"- Total flight time: {total_focus // 60}m",
            f"- Total break time: {total_break // 60}m",
        ]

        filepath.write_text("\n".join(lines), encoding="utf-8")