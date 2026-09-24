import os
import requests
from services.llm_base import LLMBase


class OpenAIService(LLMBase):
    """LLM service for any OpenAI-compatible Chat Completions API.

    Works with OpenAI itself and with compatible servers (OpenRouter, LM Studio,
    vLLM, llama.cpp server, Groq, Together, ...) by pointing base_url at them.
    The API key is read from the OPENAI_API_KEY environment variable so it never
    has to live in config.json; local servers usually don't need one.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        oa_cfg = self.config.get("openai", {})
        self.base_url = oa_cfg.get("base_url", "https://api.openai.com/v1").rstrip("/")
        self.model = oa_cfg.get("model", "gpt-4o-mini")
        self.json_mode = oa_cfg.get("json_mode", True)
        self.extended_sampling = oa_cfg.get("extended_sampling", False)
        self.max_tokens_field = oa_cfg.get("max_tokens_field", "max_tokens")
        self.max_tokens = int(oa_cfg.get("max_tokens", 512))
        self.timeout = oa_cfg.get("timeout", 120)
        self.reasoning = self._parse_toggle(oa_cfg.get("reasoning"))
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        # Standard OpenAI auth is "Authorization: Bearer <key>"; some proxies and
        # gateways expect the raw key in a custom header such as "x-api-key".
        auth_header = oa_cfg.get("auth_header", "Authorization")

        self.headers = {"Content-Type": "application/json"}
        if self.api_key:
            if auth_header.lower() == "authorization":
                self.headers[auth_header] = f"Bearer {self.api_key}"
            else:
                self.headers[auth_header] = self.api_key

        print(f"Initializing OpenAI-compatible LLM Service (model={self.model}, url={self.base_url})...")

    @staticmethod
    def _parse_toggle(value) -> bool | None:
        """Parses true/false from config or env strings; None means 'not set'."""
        if value is None or isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False
        return None

    def _chat(self, system_prompt: str, user_prompt: str, cfg: dict, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": cfg.get("temperature", 0.7),
            self.max_tokens_field: cfg.get("max_tokens", self.max_tokens),
        }

        # top_k / min_p / repeat_penalty are not part of the OpenAI spec; strict
        # providers reject them, but local servers (vLLM, llama.cpp) accept them.
        if self.extended_sampling:
            for key in ("top_k", "min_p", "repeat_penalty"):
                if key in cfg:
                    payload[key] = cfg[key]

        # Thinking toggle for reasoning models served by llama.cpp-based servers
        # (Qwen3, DeepSeek-R1, ...). Not part of the OpenAI spec, so only sent when set.
        if self.reasoning is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": self.reasoning}

        if json_mode and self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")

        choices = response.json().get("choices") or []
        if not choices:
            return ""
        content = choices[0].get("message", {}).get("content")
        if not content and choices[0].get("finish_reason") == "length":
            # Reasoning models can spend the whole budget thinking before answering.
            raise RuntimeError(
                f"Response hit the {payload[self.max_tokens_field]}-token limit before any answer "
                f"was written. Raise llm.openai.max_tokens (or OPENAI_MAX_TOKENS)."
            )
        return content.strip() if content else ""
