from llama_cpp import Llama
from services.llm_base import LLMBase


class LLMService(LLMBase):
    """LLM service using llama-cpp-python for local GGUF models."""

    def __init__(self, config: dict, model_path: str = None, chat_format: str = "auto"):
        super().__init__(config)
        llm_cfg = config.get("llm", {})
        model_path = model_path or llm_cfg.get("model_path", "./llms/model.gguf")
        chat_format = llm_cfg.get("chat_format", chat_format)
        print(f"Initializing llama-cpp LLM Service ({chat_format})...")
        self.llm = self._initialize_with_fallback(model_path, chat_format)

    def _initialize_with_fallback(self, model_path: str, chat_format: str):
        configs = [
            {"n_gpu_layers": 50, "n_ctx": 1536},
            {"n_gpu_layers": 45, "n_ctx": 1536},
            {"n_gpu_layers": 40, "n_ctx": 1536},
            {"n_gpu_layers": 35, "n_ctx": 1536},
            {"n_gpu_layers": 30, "n_ctx": 1024},
            {"n_gpu_layers": 25, "n_ctx": 1024},
            {"n_gpu_layers": 20, "n_ctx": 1024},
            {"n_gpu_layers": 15, "n_ctx": 1024},
            {"n_gpu_layers": 0,  "n_ctx": 1024},
        ]

        for cfg in configs:
            try:
                print(f"Trying config: layers={cfg['n_gpu_layers']} ctx={cfg['n_ctx']}")

                llm = Llama(
                    model_path=model_path,
                    n_gpu_layers=cfg["n_gpu_layers"],
                    n_ctx=cfg["n_ctx"],
                    chat_format=chat_format,
                    n_batch=512 if cfg["n_ctx"] <= 1024 else 1024,
                    n_threads=6,
                    verbose=False
                )

                print(f"Success with layers={cfg['n_gpu_layers']} ctx={cfg['n_ctx']}")
                return llm

            except Exception as e:
                print(f"Failed config {cfg}: {e}")

        raise RuntimeError("Could not initialize LLM with any configuration")

    def _chat(self, system_prompt: str, user_prompt: str, cfg: dict, json_mode: bool = False) -> str:
        kwargs = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": cfg.get("temperature", 0.3),
            "min_p": cfg.get("min_p", 0.05),
            "top_k": cfg.get("top_k", 40),
            "repeat_penalty": cfg.get("repeat_penalty", 1.05),
            "max_tokens": 200,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.llm.create_chat_completion(**kwargs)
        return response['choices'][0]['message']['content'].strip()
