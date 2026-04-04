import requests
from services.llm_base import LLMBase


class OllamaService(LLMBase):
    """LLM service using Ollama's REST API."""

    def __init__(self, config: dict, model: str = None, base_url: str = None):
        super().__init__(config)
        llm_cfg = config.get("llm", {})
        self.model = model or llm_cfg.get("model", "llama3.1:8b")
        self.base_url = base_url or llm_cfg.get("ollama_url", "http://localhost:11434")
        print(f"Initializing Ollama LLM Service (model={self.model}, url={self.base_url})...")

        # Verify connection
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            if self.model not in models:
                print(f"Warning: Model '{self.model}' not found. Available: {', '.join(models)}")
            else:
                print(f"Connected to Ollama. Model '{self.model}' ready.")
        except requests.ConnectionError:
            raise RuntimeError(f"Could not connect to Ollama at {self.base_url}. Is it running?")

    def _chat(self, system_prompt: str, user_prompt: str, cfg: dict, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": cfg.get("temperature", 0.3),
                "top_k": cfg.get("top_k", 40),
                "repeat_penalty": cfg.get("repeat_penalty", 1.05),
                "num_predict": 512,
            },
        }

        if json_mode:
            payload["format"] = "json"

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=120
        )
        response.raise_for_status()

        return response.json()["message"]["content"].strip()
