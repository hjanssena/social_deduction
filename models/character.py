class Character:
    def __init__(self, character_id: str, profile_data: dict):
        self.character_id = character_id
        self.name = profile_data["name"]
        self.occupation = profile_data["occupation"]
        self.bio = profile_data["bio"]
        self.archetype = profile_data["archetype"]
        self.speech_pattern = profile_data["speech_pattern"]
        self.verbal_quirks = profile_data["verbal_quirks"]
        self.is_alive = True
        self.prologue_reactions = profile_data.get("prologue_reactions", [])
        
        # Parse mechanical stats, defaulting to 5 if missing
        stats = profile_data.get("stats", {})
        self.assertion_drive = stats.get("assertion_drive", 5)
        self.contrarian_index = stats.get("contrarian_index", 5)
        self.trust_volatility = stats.get("trust_volatility", 5)
        self.logic_vs_emotion = stats.get("logic_vs_emotion", 5)