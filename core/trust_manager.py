class TrustManager:
    # Baseline modifiers on a 0-100 scale
    INTENT_MODIFIERS = {
        "defend": 10,
        "agree": 5,
        "neutral": 0,
        "question": -2,
        "deflect": -3,
        "disagree": -5,
        "accuse": -10
    }

    @staticmethod
    def calculate_shift(source: str, target: str, intent: str, characters_dict: dict) -> int:
        """
        Calculates how much the Target's trust in the Source changes based on the Source's intent.
        """
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
            # Clamp the value so it never goes below 0 or above 100
            new_trust = max(0, min(100, current_trust + shift))
            
            game_state.trust_matrix[target][source] = new_trust
            
            # Optional: Print to terminal for debugging
            trend = "++" if shift > 0 else "--"
            print(f"[Trust Shift] {target} {trend} {source} ({shift:+d}) -> New Trust: {new_trust}")