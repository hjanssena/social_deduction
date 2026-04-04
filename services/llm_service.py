import json
import re
from llama_cpp import Llama

class LLMService:
    def __init__(self, model_path: str, config: dict):
        print("Initializing LLM Service with adaptive config...")
        self.config = config.get("llm", {})
        self.llm = self._initialize_with_fallback(model_path)

    def _initialize_with_fallback(self, model_path: str):
        configs = [
            {"n_gpu_layers": 35, "n_ctx": 2048},
            {"n_gpu_layers": 30, "n_ctx": 2048},
            {"n_gpu_layers": 25, "n_ctx": 1536},
            {"n_gpu_layers": 20, "n_ctx": 1536},
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
                    chat_format="llama-3",
                    n_batch=512 if cfg["n_ctx"] <= 1024 else 1024,
                    n_threads=6,
                    verbose=False
                )

                print(f"✅ Success with layers={cfg['n_gpu_layers']} ctx={cfg['n_ctx']}")
                return llm

            except Exception as e:
                print(f"❌ Failed config {cfg}: {e}")

        raise RuntimeError("❌ Could not initialize LLM with any configuration")

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Phase 1: Cold Brain. Reads from config['llm']['logic']"""
        logic_cfg = self.config.get("logic", {})
        
        response = self.llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=logic_cfg.get("temperature", 0.3),
            min_p=logic_cfg.get("min_p", 0.05),
            top_k=logic_cfg.get("top_k", 40),
            repeat_penalty=logic_cfg.get("repeat_penalty", 1.05),
            max_tokens=2048
        )

        response_text = response['choices'][0]['message']['content'].strip()
        
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
        """Phase 2: Hot Mouth. Reads from config['llm']['narrative']"""
        narrative_cfg = self.config.get("narrative", {})
        
        response = self.llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=narrative_cfg.get("temperature", 0.7),
            min_p=narrative_cfg.get("min_p", 0.05),
            top_k=narrative_cfg.get("top_k", 40),
            repeat_penalty=narrative_cfg.get("repeat_penalty", 1.05),
            max_tokens=350 # Bump this up slightly so it has room to think AND speak!
        )
        
        raw_text = response['choices'][0]['message']['content'].strip()
        
        return raw_text