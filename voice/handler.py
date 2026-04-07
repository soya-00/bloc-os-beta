from voice.intent import IntentParser
from core.vault import Vault


class VoiceHandler:
    """
    BLOC voice command handler.
    Parses intent and executes vault actions.

    Silent — no raw print() or input() calls.
    Returns structured result dicts for the shell to display.

    Result dict:
    {
        "status":  "ok" | "cancelled" | "unknown" | "error",
        "message": "HUD-language confirmation string",
        "intent":  "the resolved intent name",
        "data":    {} optional extra data for the shell
    }
    """

    def __init__(self, vault: Vault):
        self.vault  = vault
        self.parser = IntentParser()

    def handle(self, transcript: str) -> dict:
        intent = self.parser.parse(transcript)
        name   = intent["intent"]

        # ── known intents ──────────────────────────────────

        if name == "new_note":
            path = self.vault.new_note(
                title=intent["content"][:50],
                content=intent["content"],
                tags=intent["tags"]
            )
            return {
                "status":  "ok",
                "intent":  name,
                "message": f"NOTE LOGGED · {path.name}",
                "data":    {"path": path}
            }

        elif name == "new_task":
            self.vault.new_task(
                title=intent["content"],
                due=intent["due"],
                tags=intent["tags"]
            )
            due_str = f" · DUE {intent['due']}" if intent["due"] else ""
            return {
                "status":  "ok",
                "intent":  name,
                "message": f"OBJECTIVE LOGGED · {intent['content']}{due_str}",
                "data":    {}
            }

        elif name == "new_journal":
            path = self.vault.new_journal(content=intent["content"])
            return {
                "status":  "ok",
                "intent":  name,
                "message": "FLIGHT LOG UPDATED",
                "data":    {"path": path}
            }

        elif name == "list_tasks":
            tasks = self.vault.list_tasks()
            return {
                "status":  "ok",
                "intent":  name,
                "message": f"{len(tasks)} OBJECTIVES ON RECORD",
                "data":    {"tasks": tasks}
            }

        elif name == "list_notes":
            notes = self.vault.list_notes()
            return {
                "status":  "ok",
                "intent":  name,
                "message": f"{len(notes)} RECORDS IN ARCHIVE",
                "data":    {"notes": [n.name for n in notes[:10]]}
            }

        elif name == "search":
            results = self.vault.search(intent["content"])
            return {
                "status":  "ok",
                "intent":  name,
                "message": f"{len(results)} CONTACTS FOUND · {intent['content'].upper()}",
                "data":    {"results": results[:10]}
            }
        elif intent == "new_block":
            msg = self.agenda_ui.add_from_voice(result["content"])
            return {"status": "ok", "intent": "new_block", "message": msg, "data": {}}

        elif intent == "show_agenda":
            blocks = self.agenda_ui.agenda.blocks
            lines  = [f"{b.start}→{b.end} {b.label} [{b.status}]" for b in blocks]
            return {
                "status":  "ok",
                "intent":  "show_agenda",
                "message": f"AGENDA · {len(blocks)} BLOCKS",
                "data":    {"blocks": lines},
            }

        elif name == "print_schedule":
            return {
                "status":  "ok",
                "intent":  name,
                "message": "PRINT QUEUED · AWAITING HARDWARE",
                "data":    {}
            }

        # ── unknown intent — return for shell to handle ────
        # Shell decides whether to prompt user to log as note.
        # No input() here — control stays with the shell loop.

        else:
            return {
                "status":  "unknown",
                "intent":  "unknown",
                "message": "TRANSMISSION UNRESOLVED",
                "data":    {
                    "transcript": transcript,
                    "content":    intent["content"]
                }
            }