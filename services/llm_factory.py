from services.llm_base import LLMBase


def create_llm(config: dict) -> LLMBase:
    """Factory that creates the right LLM service based on config."""
    backend = config.get("llm", {}).get("backend", "llamacpp")

    if backend == "ollama":
        from services.ollama_service import OllamaService
        return OllamaService(config)
    elif backend == "llamacpp":
        from services.llm_service import LLMService
        return LLMService(config)
    else:
        raise ValueError(f"Unknown LLM backend: '{backend}'. Use 'llamacpp' or 'ollama'.")
