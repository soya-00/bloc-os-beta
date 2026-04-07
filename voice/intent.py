import re
from datetime import datetime, timedelta


class IntentParser:
    """
    Parses raw Whisper transcript into structured intents.
    Patterns account for common Whisper mishearings and
    natural speech variations.

    Supported intents:
        new_note · new_task · new_journal
        list_tasks · list_notes · search
        print_schedule · unknown
    """

    def __init__(self):
        self.patterns = {

            "new_task": [
                # explicit triggers
                r"(?:add|create|new)\s+task[:\s]+(.+)",
                r"(?:add|create|new)\s+(?:a\s+)?to.?do[:\s]+(.+)",
                r"(?:add|create|new)\s+item[:\s]+(.+)",
                # Whisper mishearings of "task"
                r"(?:add|create|new)\s+text[:\s]+(.+)",
                r"(?:add|create|new)\s+tusk[:\s]+(.+)",
                r"(?:add|create|new)\s+task\s+(.+)",
                # natural phrasing
                r"remind me to\s+(.+)",
                r"remember to\s+(.+)",
                r"(?:i need to|i have to|i must|i should)\s+(.+)",
                r"don't let me forget to\s+(.+)",
                r"make a note to\s+(.+)",
                # shorthand
                r"todo[:\s]+(.+)",
                r"do[:\s]+(.+)",
                r"task[:\s]+(.+)",
            ],

            "new_note": [
                # explicit triggers
                r"(?:new|create|add|take a?)\s+note[:\s]+(.+)",
                r"note[:\s]+(.+)",
                r"write (?:down\s+)?(.+)",
                r"save (?:this[:\s]+)?(.+)",
                r"record[:\s]+(.+)",
                # Whisper mishearings of "note"
                r"(?:new|create|add)\s+node[:\s]+(.+)",
                r"(?:new|create|add)\s+not[:\s]+(.+)",
                # natural phrasing
                r"jot (?:down\s+)?(.+)",
                r"capture[:\s]+(.+)",
            ],

            "new_journal": [
                r"(?:journal|diary)[:\s]+(.+)",
                r"log[:\s]+(.+)",
                r"today[:\s]+(.+)",
                r"flight log[:\s]+(.+)",
                r"(?:add to|update)\s+(?:my\s+)?journal[:\s]+(.+)",
            ],

            "list_tasks": [
                r"(?:show|list|read|what are|tell me)\s+(?:my\s+)?(?:tasks|objectives|to.?dos)",
                r"what do i need to do",
                r"what's on my list",
                r"what have i got(?:\s+to do)?",
                r"show me my (?:tasks|objectives)",
                r"(?:any|what)\s+tasks\??",
            ],

            "list_notes": [
                r"(?:show|list|read)\s+(?:my\s+)?notes",
                r"what notes do i have",
                r"(?:show|open)\s+(?:my\s+)?archive",
                r"list (?:my\s+)?records",
            ],

            "search": [
                r"(?:search|find|look for|scan for)[:\s]+(.+)",
                r"(?:search|find)\s+(.+)\s+in\s+(?:my\s+)?(?:notes|vault|archive)",
                r"where (?:is|did i put|did i write)[:\s]+(.+)",
            ],

            "print_schedule": [
                r"print\s+(?:my\s+)?(?:schedule|tasks|list|agenda)",
                r"print today",
                r"(?:send to|output to)\s+printer",
            ],
        }

        from core.agenda import AGENDA_INTENT_PATTERNS
        self.patterns.update(AGENDA_INTENT_PATTERNS)
        self.due_patterns = {
            "today":     lambda: datetime.now().strftime("%Y-%m-%d"),
            "tomorrow":  lambda: (
                datetime.now() + timedelta(days=1)
            ).strftime("%Y-%m-%d"),
            "monday":    lambda: self._next_weekday(0),
            "tuesday":   lambda: self._next_weekday(1),
            "wednesday": lambda: self._next_weekday(2),
            "thursday":  lambda: self._next_weekday(3),
            "friday":    lambda: self._next_weekday(4),
            "saturday":  lambda: self._next_weekday(5),
            "sunday":    lambda: self._next_weekday(6),
            "next week": lambda: (
                datetime.now() + timedelta(weeks=1)
            ).strftime("%Y-%m-%d"),
            "this week": lambda: (
                datetime.now() + timedelta(days=4)
            ).strftime("%Y-%m-%d"),
        }

    def _next_weekday(self, weekday: int) -> str:
        """Date of next occurrence of a weekday (0=Monday)."""
        today      = datetime.now()
        days_ahead = weekday - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    def _extract_due_date(self, text: str) -> tuple[str, str]:
        """
        Extract due date phrase from text.
        Returns (cleaned_text, due_date_string).
        """
        text_lower = text.lower()

        for keyword, date_fn in self.due_patterns.items():
            patterns = [
                rf"\s+(?:by|on|due|for)\s+{keyword}",
                rf"\s+{keyword}$",
            ]
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    due     = date_fn()
                    cleaned = re.sub(
                        pattern, "", text, flags=re.IGNORECASE
                    ).strip()
                    return cleaned, due

        return text, ""

    def _extract_tags(self, text: str) -> tuple[str, list]:
        """
        Extract #hashtags from text.
        Returns (cleaned_text, tags_list).
        """
        tags    = re.findall(r"#(\w+)", text)
        cleaned = re.sub(r"#\w+", "", text).strip()
        return cleaned, tags

    def parse(self, text: str) -> dict:
        """
        Parse raw transcript into a structured intent dict.

        Returns:
        {
            "intent":  "new_task" | "new_note" | ... | "unknown",
            "content": "main content string",
            "due":     "2026-03-01" or "",
            "tags":    ["tag1", "tag2"],
            "raw":     "original transcript"
        }
        """
        text       = text.strip()
        text_lower = text.lower()

        result = {
            "intent":  "unknown",
            "content": text,
            "due":     "",
            "tags":    [],
            "raw":     text,
        }

        for intent_name, pattern_list in self.patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, text_lower)
                if match:
                    result["intent"] = intent_name
                    if match.lastindex:
                        start            = match.start(1)
                        end              = match.end(1)
                        result["content"] = text[start:end].strip()
                    break
            if result["intent"] != "unknown":
                break

        content, due  = self._extract_due_date(result["content"])
        content, tags = self._extract_tags(content)

        result["content"] = content
        result["due"]     = due
        result["tags"]    = tags

        return result