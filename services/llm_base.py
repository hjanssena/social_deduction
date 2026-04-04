import json
import re
from abc import ABC, abstractmethod


class LLMBase(ABC):
    """Abstract base for LLM services. Both llama-cpp and Ollama implement this."""

    def __init__(self, config: dict):
        self.config = config.get("llm", {})

    @abstractmethod
    def _chat(self, system_prompt: str, user_prompt: str, cfg: dict, json_mode: bool = False) -> str:
        """Send a chat completion request. Returns raw response text."""
        pass

    def generate_json(self, system_prompt: str, user_prompt: str, use_narrative_cfg: bool = False) -> dict:
        cfg = self.config.get("narrative" if use_narrative_cfg else "logic", {})
        response_text = self._chat(system_prompt, user_prompt, cfg, json_mode=True)

        # Try parsing directly first, then extract if needed
        try:
            return json.loads(response_text)
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
        return self._chat(system_prompt, user_prompt, cfg, json_mode=False)
