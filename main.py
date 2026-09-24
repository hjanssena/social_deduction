from services.llm_factory import create_llm
from services.prompt_service import PromptService
from models.character import Character
from models.characters_data import RAW_CHARACTER_DATA
from core.game_master import GameMaster
from dotenv import load_dotenv
import json
import os

# Environment variables that override machine-specific values in config.json.
ENV_OVERRIDES = {
    "LLM_BACKEND": ("llm", "backend"),
    "LLM_MODEL_PATH": ("llm", "model_path"),
    "LLM_CHAT_FORMAT": ("llm", "chat_format"),
    "OLLAMA_MODEL": ("llm", "model"),
    "OLLAMA_URL": ("llm", "ollama_url"),
    "OPENAI_BASE_URL": ("llm", "openai", "base_url"),
    "OPENAI_MODEL": ("llm", "openai", "model"),
    "OPENAI_AUTH_HEADER": ("llm", "openai", "auth_header"),
    "OPENAI_MAX_TOKENS": ("llm", "openai", "max_tokens"),
    "OPENAI_REASONING": ("llm", "openai", "reasoning"),
}


def apply_env_overrides(config: dict):
    """Overlay values from the environment (and .env, if present) onto config."""
    load_dotenv()
    for var, path in ENV_OVERRIDES.items():
        value = os.getenv(var)
        if value:
            section = config
            for key in path[:-1]:
                section = section.setdefault(key, {})
            section[path[-1]] = value

    show_logic = os.getenv("DEBUG_SHOW_LOGIC")
    if show_logic:
        config.setdefault("debug", {})["show_logic"] = show_logic.lower() in ("1", "true", "yes")


def main():
    with open("config.json", "r") as f:
        config = json.load(f)
    apply_env_overrides(config)

    # 1. Initialize Services
    llm = create_llm(config)
    prompt_builder = PromptService()
    
    # 2. Instantiate Models
    characters = [Character(f"npc_{c['name'].lower()}", c) for c in RAW_CHARACTER_DATA]
    
    # 3. Inject into GameMaster
    gm = GameMaster(llm_service=llm, prompt_service=prompt_builder, characters=characters, config=config)
    
    gm.state.public_events.append("Last night, Victor's uncle mysteriously disappeared without a trace. Victor is the town Mayor.")
    # 4. Run Day 0 Logic
    mayor_event = "[Victor (Mayor)]: 'Quiet down! My uncle has vanished...'"
    
    # FIX 1: Access chat_history through the state object
    gm.state.chat_history.append(mayor_event)
    
    # FIX 2: Kick off the actual state machine instead of a single manual reaction
    gm.run_loop()

if __name__ == "__main__":
    main()