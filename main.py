import time
from datetime import datetime
from core.vault import Vault
from core.config import Config
from voice.transcriber import Transcriber
from voice.handler import VoiceHandler
from ui.shell import Shell
from ui.environment import Environment

vault  = Vault()
config = Config(vault.dirs["config"])
env    = Environment(config)

# ─── BOOT SEQUENCE ────────────────────────────────────────

COL_WIDTH = 52          # total width before the status tag
TAG_OK      = "[ OK      ]"
TAG_STANDBY = "[ STANDBY ]"
TAG_LOADING = "[ LOADING ]"

def boot_line(label, status="ok", style="primary"):
    tag  = TAG_OK if status == "ok" else TAG_STANDBY if status == "standby" else TAG_LOADING
    dots = "·" * (COL_WIDTH - len(label) - 4)
    env.p(f"    {label} {dots} {tag}", style)
    time.sleep(0.07)

env.clear()
env.accent("    ◈ BLOC OS  v0.1\n")
env.separator()
env.accent("    INITIALIZING SYSTEMS\n")

checks = [
    ("VAULT",        "ok",      "primary"),
    ("CONFIG",       "ok",      "primary"),
    ("AGENDA",   "ok",      "primary"),
    ("TRAFFIC","ok",     "primary"),
    ("VOICE ENGINE", "ok",      "primary"),
    ("WHISPER",      "ok",      "primary"),
    ("BLUETOOTH",    "standby", "dim"),
    ("PRINTER",      "standby", "dim"),
    ("SYNC",         "standby", "dim"),
]

for label, status, style in checks:
    boot_line(label, status, style)

time.sleep(0.6)

env.separator()
env.accent(f"\n    {config.get('identity', 'boot_message', 'ALL SYSTEMS NOMINAL')}\n")
env.dim(f"    WELCOME, {config.callsign}")
env.dim(f"    {datetime.now().strftime('%A %d %B %Y  %H:%M').upper()}\n")

time.sleep(0.5)
boot_line("VOICE ENGINE", "loading", "dim")
time.sleep(1.2)

transcriber = Transcriber(model_size="small")
handler     = VoiceHandler(vault)
shell       = Shell(vault, transcriber, handler)
shell.run()