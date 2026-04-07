import os
from gpt4all import GPT4All
from services.llm_base import LLMBase

class GPT4AllService(LLMBase):
    """LLM service using GPT4All for universal hardware acceleration (CUDA/Vulkan/Metal)."""
    def __init__(self, config: dict):
        super().__init__(config)
        llm_cfg = config.get("llm", {})
        
        # Parse the full path into directory and filename
        full_path = llm_cfg.get("model_path", "./llms/model.gguf")
        model_dir, model_filename = os.path.split(full_path)
        
        if not model_dir:
            model_dir = None

        print(f"Initializing GPT4All LLM Service...")
        print(f"Loading '{model_filename}' from '{model_dir or 'default directory'}'...")
        
        self.llm = None
        for device in ["cuda", "kompute", "cpu"]:
            try:
                self.llm = GPT4All(
                    model_name=model_filename,
                    model_path=model_dir,
                    device=device,
                    allow_download=False
                )
                print(f"GPT4All loaded on: {device}")
                break
            except Exception as e:
                print(f"{device} unavailable: {e}")

        if self.llm is None:
            raise RuntimeError("Failed to initialize GPT4All on any backend.")

    def _chat(self, system_prompt: str, user_prompt: str, cfg: dict, json_mode: bool = False) -> str:
        kwargs = {
            "temp": cfg.get("temperature", 0.7),
            "top_k": cfg.get("top_k", 40),
            "top_p": cfg.get("top_p", 0.8),
            "repeat_penalty": cfg.get("repeat_penalty", 1.05),
            "max_tokens": 512,
        }
        with self.llm.chat_session(system_prompt=system_prompt):
            response = self.llm.generate(user_prompt, **kwargs)
            
        return response.strip()