import os
import sys
import time
from datetime import datetime
from core.config import Config
from core.vault import Vault
from ui.environment import Environment
from tasks.kanban_manager import KanbanManager
from ui.kanban_ui import KanbanUI
from core.pulse import Pulse
from ui.pulse_ui import PulseUI
from core.radar import Radar, LONDON_TMA
from ui.radar_ui import RadarUI
from core.sync import SyncUI
from ui.autoflight import AutoflightUI
from core.agenda import AgendaUI

if os.name == 'nt':
    import msvcrt
    def get_key():
        return msvcrt.getwch()
else:
    import tty, termios
    def get_key():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ─── VOCABULARY ───────────────────────────────────────────
# All user-facing status language lives here.
# Never scatter raw "ERROR" / "OK" strings across UI code.

V = {
    "saved":      "LOGGED",
    "deleted":    "SCRUBBED",
    "confirmed":  "CONFIRMED",
    "error":      "FAULT",
    "warning":    "CAUTION",
    "loading":    "ACQUIRING",
    "not_found":  "NO CONTACT",
    "aborted":    "ABORTED",
    "standby":    "STANDING BY",
    "complete":   "TARGET NEUTRALIZED",
    "no_signal":  "NO SIGNAL",
    "empty":      "CLEAR",
}

# ─── LANDING LINE HELPER ──────────────────────────────────
LAND_COL = 48

def _land_line(env, label, delay=0.3):
    dots = "·" * (LAND_COL - len(label) - 4)
    env.dim(f"    {label} {dots} [ OK ]")
    time.sleep(delay)


# ─── SPARKLINE HELPER ─────────────────────────────────────

def _sparkline(done: int, total: int, width: int = 8) -> str:
    """Mini filled bar — done vs total tasks."""
    if total == 0:
        return "░" * width
    filled = round((done / total) * width)
    return "█" * filled + "░" * (width - filled)


class Shell:
    def __init__(self, vault, transcriber, handler):
        self.vault = vault
        self.transcriber = transcriber
        self.handler = handler
        self.config = Config(vault.dirs["config"])
        self.env = Environment(self.config)
        self.running = True
        self.kanban_manager = KanbanManager(vault.dirs["boards"])
        self.kanban_ui = KanbanUI(self.kanban_manager, self.env)
        self.pulse = Pulse(
            self.config,
            vault.dirs.get("sessions", vault.root / "sessions")
        )
        self.pulse_ui = PulseUI(self.pulse, self.env)
        self.radar    = Radar(self.config, LONDON_TMA)
        self.radar_ui = RadarUI(self.radar, self.env)
        self.sync_ui    = SyncUI(self.vault, self.env)
        self.agenda_ui = AgendaUI(
            calendar_dir = vault.dirs.get("calendar", vault.root / "calendar"),
            env          = self.env,
            config       = self.config,
        )
        self.autoflight_ui = AutoflightUI(
            vault  = self.vault,
            config = self.config,
        )
    def clear(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    # ─── HEADER ───────────────────────────────────────────

    def header(self, page: str = "COMMAND MENU"):
        """
        Permanent instrument strip.
        Fixed-width fields — same layout on every screen.
        page = breadcrumb label shown right-aligned on second row.
        """
        now      = datetime.now().strftime("%H:%M:%S")
        date     = datetime.now().strftime("%a %d %b %Y").upper()
        stats    = self.vault.stats()
        callsign = self.config.callsign
        bat_bar  = self.env.bar(0.84, width=8)
        agenda_status = self.agenda_ui.status_line()
        wake     = self.config.wake_word.upper()
        spark    = _sparkline(stats["tasks"], max(stats["tasks"], 1))

        self.env.clear()

        # ── instrument strip (accent / yellow) ────────────
        self.env.accent(
            f"    {self.env.char('corner_tl')} BLOC OS"
            f"    HDG [{now}]"
            f"    [{callsign}]"
            f"    TKS [{spark}] {stats['tasks']:02d}"
            f"    BAT [{bat_bar}] 84%"
            f"    AGD [{agenda_status}]"
        )
        # double separator = structural frame
        self.env.separator("double")

        # ── breadcrumb row (dim) ───────────────────────────
        left  = f"    {date}    NTS {stats['notes']:02d}    WAKE [{wake}]"
        right = f"[ {page.upper()} ]"
        pad   = max(1, 72 - len(left) - len(right))
        self.env.dim(f"{left}{' ' * pad}{right}")
        self.env.separator()
        print()

    def menu(self):
        c = self.env.char
        self.env.accent(f"    {c('corner_tl')} COMMAND MENU\n")

        # ── INPUT ─────────────────────────────────────────
        self.env.dim(f"    ── INPUT ────────────────────────────────")
        self.env.primary(f"    v  ·  radio input")
        self.env.primary(f"    n  ·  new note")
        self.env.primary(f"    t  ·  new objective")
        print()

        # ── REVIEW ────────────────────────────────────────
        self.env.dim(f"    ── REVIEW ───────────────────────────────")
        self.env.primary(f"    l  ·  list objectives")
        self.env.primary(f"    c  ·  mark objective complete")
        self.env.primary(f"    d  ·  delete objective")
        self.env.primary(f"    o  ·  open flight archive")
        print()

        # ── SYSTEMS ───────────────────────────────────────
        self.env.dim(f"    ── SYSTEMS ──────────────────────────────")
        self.env.primary(f"    a  ·  agenda")
        self.env.primary(f"    f  ·  traffic air time")
        self.env.primary(f"    k  ·  mission boards")
        self.env.primary(f"    p  ·  pulse · focus timer")
        self.env.primary(f"    x  ·  radar · london tma")
        self.env.primary(f"    s  ·  settings")
        self.env.primary(f"    q  ·  touchdown")

        print()

        # ── CMD input zone ────────────────────────────────
        self.env.separator("double")
        self.env.accent(f"    CMD {c('arrow_rt')} ", end="")

    def draw(self):
        self.header("COMMAND MENU")
        self.menu()

    # ─── ACTIONS ──────────────────────────────────────────


    def do_voice(self):
        self.env.clear()
        self.header("RADIO · VOICE INPUT")
        self.env.dim("    ◈ SPEAK · HOLD SILENCE TO CLOSE CHANNEL\n")

        text = self.transcriber.listen_and_transcribe()

        if not text:
            self.env.alert(f"    ◈ RADIO ················· {V['no_signal']}")
            self._pause()
            return

        result = self.handler.handle(text)
        print()

        if result["status"] == "ok":
            self.env.accent(
                f"    ◈ {V['confirmed']} ············· {result['message']}"
            )

            # ── display list data if returned ──────────────
            data = result.get("data", {})

            if result["intent"] == "list_tasks" and data.get("tasks"):
                print()
                for task in data["tasks"]:
                    self.env.primary(
                        f"    {self.env.char('bullet')}  {task}"
                    )

            elif result["intent"] == "list_notes" and data.get("notes"):
                print()
                for name in data["notes"]:
                    self.env.primary(f"    {self.env.char('bullet')}  {name}")

            elif result["intent"] == "search" and data.get("results"):
                print()
                for filepath, line_num, line in data["results"]:
                    self.env.primary(
                        f"    {self.env.char('bullet')}  "
                        f"{filepath.name}  LN{line_num}  {line[:40]}"
                    )

        elif result["status"] == "unknown":
            # ── unresolved intent — offer to log as note ───
            self.env.alert(
                f"    ◈ {V['not_found']} ·········· TRANSMISSION UNRESOLVED"
            )
            self.env.dim(f"    ◈ HEARD ················ {text.upper()}")
            print()
            self.env.separator("double")
            self.env.accent(
                f"    LOG AS QUICK NOTE? ···· [y/n] : ", end=""
            )
            # Temporarily restore normal input (not raw key)
            confirm = input().strip().lower()
            if confirm == 'y':
                self.vault.new_note(
                    title="Quick note",
                    content=result["data"].get("content", text),
                    tags=["voice", "unsorted"]
                )
                self.env.accent(
                    f"\n    ◈ TRANSMISSION ·········· {V['saved']}"
                )
            else:
                self.env.dim(
                    f"    ◈ TRANSMISSION ·········· {V['aborted']}"
                )

        self._pause()

    def do_new_note(self):
        """
        Writing screen — defined bordered input area with live word count.
        """
        self.env.clear()
        self.header("ARCHIVE · NEW NOTE")

        self.env.accent("    ◈ CALLSIGN / TITLE ····· ", end="")
        title = input().strip()
        if not title:
            return

        self.env.dim("    ◈ TAGS ················· (space separated): ", end="")
        tags_raw = input().strip()
        tags = tags_raw.split() if tags_raw else []

        # ── writing area ──────────────────────────────────
        print()
        self.env.separator("double")
        self.env.accent(f"    ◈ TRANSMISSION OPEN ···· {title.upper()}")
        self.env.dim( f"    ◈ DOUBLE ENTER TO CLOSE CHANNEL")
        self.env.separator("double")
        print()

        lines      = []
        word_count = 0

        while True:
            self.env.primary("    ▶ ", end="")
            line = input()

            if line == "" and lines and lines[-1] == "":
                break

            lines.append(line)
            word_count = sum(len(l.split()) for l in lines)
            self.env.dim(f"    ···················· WC [{word_count:04d}]")

        content = "\n".join(lines).strip()

        self.env.separator("double")
        self.env.dim(
            f"    ◈ CHANNEL CLOSED ······ "
            f"WC [{word_count:04d}]  ·  "
            f"TAGS [{' '.join(tags) if tags else 'NONE'}]"
        )
        self.vault.new_note(title=title, content=content, tags=tags)
        self.env.accent(f"\n    ◈ TRANSMISSION ·········· {V['saved']}")
        self._pause()

    def do_new_task(self):
        self.env.clear()
        self.header("OBJECTIVES · NEW")
        self.env.accent("    ◈ OBJECTIVE ············ ", end="")
        title = input().strip()
        if not title:
            return
        self.env.dim("    ◈ DUE DATE ············· (yyyy-mm-dd or blank): ", end="")
        due = input().strip()
        self.env.dim("    ◈ TAGS ················· (space separated): ", end="")
        tags_raw = input().strip()
        tags = tags_raw.split() if tags_raw else []
        self.vault.new_task(title=title, due=due, tags=tags)
        self.env.accent(f"\n    ◈ OBJECTIVE ············ {V['saved']} · {V['standby']}")
        self._pause()

    def do_list_tasks(self):
        self.env.clear()
        self.header("OBJECTIVES · ACTIVE")
        tasks = self.vault.list_tasks()
        if tasks:
            for i, task in enumerate(tasks, 1):
                self.env.primary(f"    {self.env.char('bullet')}  {i:02d}  {task}")
        else:
            self.env.dim(
                f"    ◈ OBJECTIVES ··········· {V['empty']} · NO ACTIVE TARGETS"
            )
        self._pause()

    def do_complete_task(self):
        self.env.clear()
        self.header("OBJECTIVES · COMPLETE")
        tasks = self.vault.list_tasks()
        if not tasks:
            self.env.dim(f"    ◈ OBJECTIVES ··········· {V['empty']}")
            self._pause()
            return
        for i, task in enumerate(tasks, 1):
            self.env.primary(f"    {self.env.char('bullet')}  {i:02d}  {task}")
        print()
        self.env.accent("    ◈ TARGET NUMBER ········ ", end="")
        try:
            index = int(input().strip())
            success = self.vault.complete_task(index)
            if success:
                self.env.accent(f"\n    ◈ OBJECTIVE ············ {V['complete']}")
            else:
                self.env.alert(f"    ◈ {V['error']} ················ INVALID TARGET")
        except ValueError:
            self.env.alert(f"    ◈ {V['error']} ················ INVALID INPUT")
        self._pause()

    def do_delete_task(self):
        self.env.clear()
        self.header("OBJECTIVES · DELETE")
        tasks = self.vault.list_tasks()
        if not tasks:
            self.env.dim(f"    ◈ OBJECTIVES ··········· {V['empty']}")
            self._pause()
            return
        for i, task in enumerate(tasks, 1):
            self.env.primary(f"    {self.env.char('bullet')}  {i:02d}  {task}")
        print()
        self.env.accent("    ◈ TARGET NUMBER ········ ", end="")
        try:
            index = int(input().strip())
            self.env.alert(
                f"    ◈ {V['warning']} ············· CONFIRM DELETION [y/n] : ",
                end=""
            )
            if input().strip().lower() == 'y':
                success = self.vault.delete_task(index)
                if success:
                    self.env.accent(f"\n    ◈ OBJECTIVE ············ {V['deleted']}")
                else:
                    self.env.alert(f"    ◈ {V['error']} ················ INVALID TARGET")
            else:
                self.env.dim(f"    ◈ DELETION ············· {V['aborted']}")
        except ValueError:
            self.env.alert(f"    ◈ {V['error']} ················ INVALID INPUT")
        self._pause()

    def do_list_files(self):
        self.env.clear()
        self.header("ARCHIVE · FLIGHT RECORDS")
        self.env.primary("    1  ·  notes")
        self.env.primary("    2  ·  journal")
        self.env.primary("    3  ·  tasks")
        self.env.primary("    4  ·  archive")
        print()
        self.env.accent("    ◈ SELECT BAY ··········· ", end="")
        choice = input().strip()

        folder_map = {
            "1": "notes", "2": "journal",
            "3": "tasks",  "4": "archive", "": "notes",
        }
        folder = folder_map.get(choice, "notes")
        files  = self.vault.list_files(folder)

        print()
        self.env.accent(
            f"    ◈ {folder.upper()} ················ "
            f"{len(files)} RECORDS ON FILE"
        )
        self.env.separator()
        print()

        if not files:
            self.env.dim(f"    ◈ ARCHIVE ··············· {V['empty']}")
        else:
            for i, f in enumerate(files, 1):
                self.env.primary(f"    {i:02d}  {f['name']}")
                self.env.dim(
                    f"         {f['modified']}"
                    f"  ·  {f['words']} words"
                )
                print()

        if files:
            self.env.separator()
            self.env.accent(
                "    ◈ OPEN RECORD ·········· (number or blank): ", end=""
            )
            choice = input().strip()
            try:
                index = int(choice) - 1
                if 0 <= index < len(files):
                    if os.name == 'nt':
                        os.system(f'notepad "{files[index]["path"]}"')
                    else:
                        os.system(f'micro "{files[index]["path"]}"')
            except ValueError:
                pass

        self._pause()

    def _pause(self):
        print()
        self.env.dim(f"    ◈ {V['standby']} ·········· PRESS ANY KEY")
        get_key()


    # ─── MAIN LOOP ────────────────────────────────────────

    def run(self):
        from ui.settings_ui import SettingsUI
        self.settings_ui = SettingsUI(self.config, self.env)

        while self.running:
            self.draw()
            key = get_key().lower()

            if key == 'v':
                self.do_voice()
            elif key == 'f':
                self.autoflight_ui.run()
            elif key == 'a':
                self.agenda_ui.run()
            elif key == 'n':
                self.do_new_note()
            elif key == 't':
                self.do_new_task()
            elif key == 'l':
                self.do_list_tasks()
            elif key == 'c':
                self.do_complete_task()
            elif key == 'd':
                self.do_delete_task()
            elif key == 'o':
                self.do_list_files()
            elif key == 'k':
                self.kanban_ui.show_board_picker()
            elif key == 'x':
                self.radar_ui.run()
            elif key == 'p':
                self.pulse_ui.run()
            elif key == 's':
                self.settings_ui.run()
            elif key == 'q':
                self.env.clear()
                self.env.separator("double")
                self.env.accent("\n    ◈ BLOC OS\n")
                self.env.accent("    INITIATING LANDING SEQUENCE\n")
                _land_line(self.env, "SAVING FLIGHT DATA",    0.3)
                _land_line(self.env, "SECURING VAULT",        0.3)
                _land_line(self.env, "VOICE ENGINE OFFLINE",  0.3)
                _land_line(self.env, "SYSTEMS STANDING DOWN", 0.4)
                self.env.separator("double")
                self.env.accent(
                    f"\n    TOUCHDOWN  ·  {self.config.callsign}"
                    f"  ·  LANDING...\n"
                )
                time.sleep(1.5)
                self.running = False