class TrustManager:
    TRUST_MIN = 0
    TRUST_MAX = 100
    TRUST_NEUTRAL = 50
    TRUST_HOSTILE_THRESHOLD = 30
    TRUST_SUSPICIOUS_THRESHOLD = 45
    TRUST_FRIENDLY_THRESHOLD = 55
    TRUST_ALLIED_THRESHOLD = 75

    # Baseline modifiers on a 0-100 scale
    INTENT_MODIFIERS = {
        "agree": 5,             # Target likes that you agree with them
        "defend_other": 8,      # Target loves that you protected them
        "accuse": -8,           # Target hates that you accused them
        "disagree": -3,         # Target dislikes that you argue with them
        "defend_self": -2,      # Target is slightly annoyed you are resisting their accusation
        "deflect": -4,          # Target thinks you are being shady
        "question": 0,          # Neutral — information-seeking, not an attack
        "neutral": 0,            # No effect
        "vote_lynch": -25
    }

    @staticmethod
    def calculate_shift(source: str, target: str, intent: str, characters_dict: dict) -> int:
        """
        Calculates how much the Target's trust in the Source changes based on the Source's intent.
        """
        # Fetch the base shift from the updated dictionary
        base_shift = TrustManager.INTENT_MODIFIERS.get(intent, 0)
        
        if base_shift == 0:
            return 0

        multiplier = 1.0
        
        # If the target is an NPC, apply their personal trust volatility
        if target in characters_dict:
            target_obj = characters_dict[target]
            # Volatility is 1-10. 5 is baseline (1.0x). 
            # 10 is 2.0x (double swing). 1 is 0.2x (tiny swing).
            multiplier = max(0.2, target_obj.trust_volatility / 5.0)

        # We return the mathematically scaled integer
        return int(base_shift * multiplier)

    @staticmethod
    def apply_interaction(game_state, source: str, target: str, intent: str, characters_dict: dict):
        """
        Applies the shift to the actual GameState Trust Matrix and clamps it between 0 and 100.
        """
        if target == "None" or target not in game_state.trust_matrix or target == source:
            return

        # Target's opinion of the Source changes
        shift = TrustManager.calculate_shift(source, target, intent, characters_dict)
        
        if shift != 0:
            current_trust = game_state.trust_matrix[target][source]
            new_trust = max(TrustManager.TRUST_MIN, min(TrustManager.TRUST_MAX, current_trust + shift))
            
            game_state.trust_matrix[target][source] = new_trust
            
            if shift > 0:
                print(f"{target} has increased their trust in {source}")
            elif shift < 0:
                print(f"{target} has decreased their trust in {source}")

    @staticmethod
    def get_relationship_prompt(trust_score: int) -> str:
        """Translates a numerical trust score into an LLM behavioral prompt."""
        if trust_score < TrustManager.TRUST_HOSTILE_THRESHOLD:
            return "You deeply distrust and despise them. Be openly hostile or dismissive."
        elif trust_score < TrustManager.TRUST_SUSPICIOUS_THRESHOLD:
            return "You are suspicious of them. Question their motives and be guarded."
        elif trust_score <= TrustManager.TRUST_FRIENDLY_THRESHOLD:
            return "You are emotionally neutral towards them."
        elif trust_score < TrustManager.TRUST_ALLIED_THRESHOLD:
            return "You trust them. Be supportive and inclined to agree with them."
        else:
            return "You completely trust them with your life. Defend them aggressively."
        
    @staticmethod
    def get_all_relationships_prompt(character_name: str, game_state) -> str:
        """Generates a text summary of a character's strongest feelings towards others."""
        if character_name not in game_state.trust_matrix:
            return ""
            
        relationships = []
        for other_name, trust_score in game_state.trust_matrix[character_name].items():
            if other_name == character_name:
                continue

            if trust_score < TrustManager.TRUST_HOSTILE_THRESHOLD:
                relationships.append(f"You deeply distrust and despise {other_name}.")
            elif trust_score < TrustManager.TRUST_SUSPICIOUS_THRESHOLD:
                relationships.append(f"You are highly suspicious of {other_name}.")
            elif trust_score >= TrustManager.TRUST_ALLIED_THRESHOLD:
                relationships.append(f"You completely trust and will protect {other_name}.")
            elif trust_score >= TrustManager.TRUST_FRIENDLY_THRESHOLD:
                relationships.append(f"You generally trust {other_name}.")

        if relationships:
            return " ".join(relationships)
        return "You currently have neutral feelings towards everyone."
    
    # Opinion labels: keyed by (trust_tier, last_intent_toward_me)
    # trust_tier: "hostile", "suspicious", "neutral", "friendly", "allied"
    # Falls back to trust-only opinion if no interaction found
    TRUST_OPINIONS = {
        "hostile": "Dangerous, don't trust",
        "suspicious": "Suspicious, watching closely",
        "neutral": "No strong feelings",
        "friendly": "Seems trustworthy",
        "allied": "Trusted ally, will defend",
    }

    INTENT_OPINION_MODIFIERS = {
        "accuse": "Accused me",
        "defend_other": "Defended me",
        "agree": "Sided with me",
        "disagree": "Argued against me",
        "vote_lynch": "Voted to kill me",
        "defend_self": "Denied my claims",
        "deflect": "Dodged my question",
    }

    @staticmethod
    def get_trust_tier(trust_score: int) -> str:
        if trust_score < TrustManager.TRUST_HOSTILE_THRESHOLD:
            return "hostile"
        elif trust_score < TrustManager.TRUST_SUSPICIOUS_THRESHOLD:
            return "suspicious"
        elif trust_score <= TrustManager.TRUST_FRIENDLY_THRESHOLD:
            return "neutral"
        elif trust_score < TrustManager.TRUST_ALLIED_THRESHOLD:
            return "friendly"
        else:
            return "allied"

    @staticmethod
    def compute_opinions(game_state) -> dict:
        """Derives short opinion tags for each character about every other character.
        Returns {viewer: {target: "short opinion"}}."""
        opinions = {}
        for viewer in game_state.alive_characters:
            opinions[viewer] = {}
            if viewer not in game_state.trust_matrix:
                continue
            for target in game_state.alive_characters:
                if target == viewer:
                    continue
                trust_score = game_state.trust_matrix[viewer].get(target, 50)
                tier = TrustManager.get_trust_tier(trust_score)
                base_opinion = TrustManager.TRUST_OPINIONS[tier]

                # Find last interaction from target toward viewer in logical history
                last_intent = None
                for entry in reversed(game_state.logical_history):
                    if entry.startswith(f"{target} ["):
                        # Extract intent: "Name [intent] -> ..."
                        try:
                            intent = entry.split("[")[1].split("]")[0]
                            entry_target = entry.split("-> ")[1].split(" ")[0]
                            if entry_target == viewer:
                                last_intent = intent
                                break
                        except (IndexError, ValueError):
                            continue

                modifier = TrustManager.INTENT_OPINION_MODIFIERS.get(last_intent)
                if modifier:
                    opinions[viewer][target] = f"{modifier}. {base_opinion}"
                else:
                    opinions[viewer][target] = base_opinion

        return opinions

    @staticmethod
    def apply_global_trust_shift(game_state, target: str, shift: int):
        """Applies a trust shift from all alive NPCs towards a single target."""
        for npc in game_state.alive_characters:
            if npc != target and npc != "Player":
                current_trust = game_state.trust_matrix[npc].get(target, TrustManager.TRUST_NEUTRAL)
                new_trust = max(TrustManager.TRUST_MIN, min(TrustManager.TRUST_MAX, current_trust + shift))
                game_state.trust_matrix[npc][target] = new_trust
                
        if shift > 0:
            print(f"The whole town now trusts you more!")
        elif shift < 0:
            print(f"The whole town now trusts you less!")