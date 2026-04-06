"""ServerIOHandler — event-queue based IOHandler for the FastAPI server.

Instead of printing to the terminal, every structured method puts a typed dict
on an outbound event queue.  Prompt methods additionally block on an inbound
response queue so the game engine thread pauses until the client sends a reply.
"""

import queue
from core.io_handler import IOHandler


class ServerIOHandler(IOHandler):
    def __init__(self):
        self.event_queue: queue.Queue = queue.Queue()
        self.response_queue: queue.Queue = queue.Queue()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _put(self, event: dict):
        self.event_queue.put(event)

    def _prompt_event(self, event: dict) -> str:
        """Put a prompt event and block until the client responds."""
        self._put(event)
        return self.response_queue.get()  # blocks

    # ------------------------------------------------------------------
    # Display methods — fire-and-forget events
    # ------------------------------------------------------------------

    def display(self, text: str):
        # Fallback for any raw display calls that slip through
        self._put({"type": "system", "text": text, "style": "info"})

    def show_dialogue(self, speaker, target, text, intent=None, emotion=None):
        self._put({
            "type": "dialogue",
            "speaker": speaker,
            "target": target,
            "text": text,
            "intent": intent,
            "emotion": emotion,
        })

    def show_reaction(self, speaker, target, text, intent=None, emotion=None, intensity=None):
        self._put({
            "type": "reaction",
            "speaker": speaker,
            "target": target,
            "text": text,
            "intent": intent,
            "emotion": emotion,
            "intensity": intensity,
        })

    def show_reveal(self, speaker, role, text):
        self._put({"type": "reveal", "speaker": speaker, "role": role, "text": text})

    def show_report(self, speaker, role, text):
        self._put({"type": "report", "speaker": speaker, "role": role, "text": text})

    def show_primer(self, text):
        self._put({"type": "primer", "speaker": "Town Crier", "text": text})

    def show_narration(self, text):
        self._put({"type": "narration", "text": text})

    def show_system(self, text, style="info"):
        self._put({"type": "system", "text": text, "style": style})

    def show_phase(self, name, day):
        self._put({"type": "phase", "name": name, "day": day})

    def show_engine_debug(self, speaker, intent, target, emotion, reasoning, intensity=None):
        self._put({
            "type": "engine_debug",
            "speaker": speaker,
            "intent": intent,
            "target": target,
            "emotion": emotion,
            "reasoning": reasoning,
            "intensity": intensity,
        })

    def show_vote(self, voter, target, thoughts=""):
        self._put({"type": "vote", "voter": voter, "target": target, "thoughts": thoughts})

    def show_death(self, name, cause, role=None):
        self._put({"type": "death", "name": name, "cause": cause, "role": role})

    def show_final_words(self, speaker, text):
        self._put({"type": "final_words", "speaker": speaker, "text": text})

    def show_game_over(self, result, message=""):
        self._put({"type": "game_over", "result": result, "message": message})

    def show_role_reveal_private(self, role, details=None):
        self._put({"type": "role_reveal_private", "role": role, "details": details or []})

    # ------------------------------------------------------------------
    # Prompt methods — block until the client responds
    # ------------------------------------------------------------------

    def pause(self, text=""):
        self._prompt_event({"type": "pause", "message": text})

    def prompt(self, text):
        return self._prompt_event({"type": "prompt", "message": text})

    def prompt_assertion(self):
        return self._prompt_event({"type": "prompt_assertion"})

    def prompt_reaction(self, speaker):
        return self._prompt_event({"type": "prompt_reaction", "speaker": speaker})

    def prompt_reaction_forced(self, speaker):
        return self._prompt_event({"type": "prompt_reaction_forced", "speaker": speaker})

    def prompt_menu(self, title, options, context=""):
        resp = self._prompt_event({
            "type": "prompt_menu",
            "title": title,
            "options": options,
            "context": context,
        })
        # Client sends back the index as a string
        try:
            idx = int(resp)
        except (ValueError, TypeError):
            idx = 0
        return max(0, min(idx, len(options) - 1))

    def prompt_final_words(self):
        return self._prompt_event({"type": "prompt_final_words"})
