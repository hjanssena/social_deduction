# Assuming your GameMaster is initialized as 'gm' and Elias, Silas, Victor are alive
from core.game_master import GameMaster
from models.character import Character
from services.llm_service import LLMService
from services.prompt_service import PromptService

RAW_CHARACTER_DATA = [
    {
        "name": "Elias",
        "occupation": "Village Blacksmith",
        "bio": "Elias has worked the forge his entire life. He is physically imposing but deeply distrustful of outsiders and magic.",
        "archetype": "Paranoid, aggressive, and blunt.",
        "speech_pattern": "Keep responses strictly under 3 sentences. Use harsh, direct language. Do not use complex words.",
        "verbal_quirks": "Often expresses doubt. Uses metaphors related to heat, fire, iron, or striking."
    },
    {
        "name": "Silas",
        "occupation": "Scholar / Record Keeper",
        "bio": "Silas considers himself the only truly educated person in the village. He views the current crisis as a puzzle to be solved.",
        "archetype": "Arrogant, cold, and highly analytical.",
        "speech_pattern": "Speak in slightly longer, well-structured sentences. Use formal and precise vocabulary. Act condescendingly.",
        "verbal_quirks": "Frequently starts sentences with 'Actually,' 'Logically,' or 'If you had paid attention.'"
    }
]

test_inputs = [
    "I saw Elias sneaking around the forge late last night, he's hiding something!",
    "Actually, Silas makes a good point, we shouldn't rush to judgment.",
    "I was asleep in my bed the whole time, I have no idea what happened.",
    "Wait, are we sure it was wolf tracks?"
]

print("--- TESTING INTENT INTERPRETER ---")
llm = LLMService(model_path="./Qwen2.5-7B-q4_k_m.gguf")
prompt_builder = PromptService()
characters = [Character(f"npc_{c['name'].lower()}", c) for c in RAW_CHARACTER_DATA]
gm = GameMaster(llm_service=llm, prompt_service=prompt_builder, characters=characters)
for text in test_inputs:
    print(f"\nRaw Input: {text}")
    result = gm.parse_player_intent(text)
    print(f"Parsed JSON: {result}")