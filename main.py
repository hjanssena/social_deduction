from services.llm_factory import create_llm
from services.prompt_service import PromptService
from models.character import Character
from models.characters_data import RAW_CHARACTER_DATA
from core.game_master import GameMaster
import json


def main():
    with open("config.json", "r") as f:
        config = json.load(f)

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