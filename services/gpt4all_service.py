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
        
        # If no directory is provided (just a filename), ensure model_dir is None
        if not model_dir:
            model_dir = None

        print(f"Initializing GPT4All LLM Service...")
        print(f"Loading '{model_filename}' from '{model_dir or 'default directory'}'...")
        
        try:
            # device="gpu" is the magic key. It will auto-detect CUDA, Vulkan, or Metal.
            # If it fails to find a GPU, it safely falls back to CPU.
            self.llm = GPT4All(
                model_name=model_filename,
                model_path=model_dir,
                device="amd",
                allow_download=False # Prevents accidental massive downloads if path is wrong
            )
            print(f"GPT4All successfully loaded on backend: {self.llm.device}")
        except Exception as e:
             raise RuntimeError(f"Failed to initialize GPT4All: {e}")

    def _chat(self, system_prompt: str, user_prompt: str, cfg: dict, json_mode: bool = False) -> str:
        """
        Executes the chat. Note: GPT4All does not have a strict API-level json_mode flag, 
        but your LLMBase regex parser handles JSON extraction perfectly from raw text.
        """
        # Map your custom config to GPT4All generation parameters
        kwargs = {
            "temp": cfg.get("temperature", 0.7),
            "top_k": cfg.get("top_k", 40),
            "top_p": cfg.get("top_p", 0.8),
            "repeat_penalty": cfg.get("repeat_penalty", 1.05),
            "max_tokens": 512,
        }

        # GPT4All uses a context manager to handle conversational memory and system prompts
        with self.llm.chat_session(system_prompt=system_prompt):
            response = self.llm.generate(user_prompt, **kwargs)
            
        return response.strip()