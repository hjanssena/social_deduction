import json
from llama_cpp import Llama

class LLMService:
    def __init__(self, model_path: str):
        print("Initializing LLM Service...")
        self.llm = Llama(
            model_path=model_path,
            n_gpu_layers=-1,
            n_ctx=4096,
            verbose=False
        )

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Sends prompts to the local model and forces a JSON response."""
        response = self.llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=150
        )
        
        response_text = response['choices'][0]['message']['content']
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON: {response_text}")
            return {}