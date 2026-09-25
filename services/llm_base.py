import json
import re
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager

# Set to True on a thread whose LLM calls may wait: see core/background.py
BACKGROUND = threading.local()


class PriorityGate:
    """Lets one LLM call through at a time. Foreground calls (anything the player is waiting on)
    always go before background ones (log entries, compaction); background calls only start
    when no foreground call is running or waiting."""

    def __init__(self):
        self._cond = threading.Condition()
        self._busy = False
        self._foreground_waiting = 0

    @contextmanager
    def hold(self):
        background = getattr(BACKGROUND, "active", False)
        with self._cond:
            if background:
                while self._busy or self._foreground_waiting:
                    self._cond.wait()
            else:
                self._foreground_waiting += 1
                while self._busy:
                    self._cond.wait()
                self._foreground_waiting -= 1
            self._busy = True
        try:
            yield
        finally:
            with self._cond:
                self._busy = False
                self._cond.notify_all()


class LLMBase(ABC):
    """Abstract base for LLM services. Both llama-cpp and Ollama implement this."""

    def __init__(self, config: dict):
        self.config = config.get("llm", {})
        self._gate = PriorityGate()

    @abstractmethod
    def _chat(self, system_prompt: str, user_prompt: str, cfg: dict, json_mode: bool = False) -> str:
        """Send a chat completion request. Returns raw response text."""
        pass

    @staticmethod
    def _sanitize_json_text(text: str) -> str:
        """Fix common LLM JSON quirks: curly/smart quotes → straight quotes."""
        text = text.replace("\u201c", '"').replace("\u201d", '"')  # " "
        text = text.replace("\u2018", "'").replace("\u2019", "'")  # ' '
        return text

    def generate_json(self, system_prompt: str, user_prompt: str, use_narrative_cfg: bool = False) -> dict:
        cfg = self.config.get("narrative" if use_narrative_cfg else "logic", {})
        with self._gate.hold():
            try:
                response_text = self._chat(system_prompt, user_prompt, cfg, json_mode=True)
            except Exception as e:
                print(f"\033[91m[Error] LLM _chat failed: {e}\033[0m", flush=True)
                return {}
        if not response_text or response_text.isspace():
            print(f"\033[91m[Error] LLM returned empty response.\033[0m")
            return {}
        response_text = self._sanitize_json_text(response_text)

        # Try parsing directly first, then extract if needed. Only JSON objects count:
        # a bare JSON string or number would break every caller's .get().
        try:
            parsed = json.loads(response_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Non-greedy extraction: find the first complete top-level JSON object
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        print(f"\033[91m[Error] Failed to parse JSON. Raw LLM output:\n{response_text}\033[0m")
        return {}

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        cfg = self.config.get("narrative", {})
        with self._gate.hold():
            try:
                result = self._chat(system_prompt, user_prompt, cfg, json_mode=False)
                return result if result else ""
            except Exception as e:
                print(f"\033[91m[Error] LLM generate_text failed: {e}\033[0m", flush=True)
                return ""
