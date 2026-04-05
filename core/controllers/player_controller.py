from core.trust_manager import TrustManager
from services.prompt_service import VALID_INTENTS

class PlayerController:
    def __init__(self, gm):
        self.gm = gm

    @property
    def io(self):
        return self.gm.io

    def get_status(self, current_assertion: int) -> str:
        """Determines if the player is violating the action thresholds."""
        actions = self.gm.state.player_actions_today
        max_actions = self.gm.config.get("player_max_actions", 4)
        min_actions = self.gm.config.get("player_min_actions", 2)
        max_assertions = self.gm.config.get("max_assertions_per_day", 8)

        if actions > max_actions:
            return "dominating"
        elif current_assertion >= (max_assertions // 2) and actions < min_actions:
            return "silent"
        return "normal"

    def parse_intent(self, player_text: str) -> dict:
        """Sends the player's raw text to the LLM to extract gameplay intent."""
        if not player_text.strip():
            return {"intent": "neutral", "target": "None", "summary": "Remained silent"}

        roster_text = self.gm.get_roster_text(viewer="Player")
        system_prompt = self.gm.prompt_builder.build_intent_parser_prompt(
            player_text=player_text,
            alive_characters=self.gm.state.alive_characters,
            chat_history=self.gm.state.chat_history,
            roster_text=roster_text
        )

        user_prompt = "Parse my text according to the rules and output the JSON."
        self.io.display("\n\033[90m[System] Parsing Player Intent...\033[0m")

        parsed_data = self.gm.llm.generate_json(system_prompt, user_prompt)

        raw_target = parsed_data.get("target", "None")
        safe_target = self.gm.sanitize_target(raw_target)

        if raw_target != "None" and safe_target == "None":
            self.io.display(f"\033[93m[Warning] LLM hallucinated target '{raw_target}'. Defaulting to 'None'.\033[0m")

        parsed_data["target"] = safe_target

        if parsed_data.get("intent") not in VALID_INTENTS.split("|"):
            self.io.display(f"\033[93m[Warning] Invalid intent '{parsed_data.get('intent')}'. Defaulting to 'neutral'.\033[0m")
            parsed_data["intent"] = "neutral"

        return parsed_data

    def process_input(self, player_text: str) -> dict:
        """Handles the full pipeline of a player's turn."""
        self.gm.state.player_actions_today += 1

        max_actions = self.gm.config.get("player_max_actions", 4)
        if self.gm.state.player_actions_today > max_actions:
            penalty = -abs(self.gm.config.get("global_trust_penalty", 5))
            self.io.display("\n\033[91m[System] The town grows highly suspicious of your constant interjections...\033[0m")
            TrustManager.apply_global_trust_shift(self.gm.state, "Player", penalty)

        parsed_data = self.parse_intent(player_text)
        intent = parsed_data.get("intent", "neutral")
        target = self.gm.sanitize_target(parsed_data.get("target", "None"))

        emotion = parsed_data.get("emotion", "neutral")
        summary = parsed_data.get("summary", "Spoke to the room.")

        TrustManager.apply_interaction(
            game_state=self.gm.state,
            source="Player",
            target=target,
            intent=intent,
            characters_dict=self.gm.characters
        )

        self.gm.state.logical_history.append(f"Player [{intent}] -> {target} (Emotion: {emotion}). Reason: {summary}")

        display_target = target if target != "None" else "Room"
        self.gm.state.chat_history.append(f"[Player -> {display_target}]: {player_text}")

        return parsed_data

    def get_vote(self) -> str:
        """Displays a menu for the player to cast their vote."""
        self.io.display("\n\033[36m" + "="*50)
        self.io.display("                 THE VOTING PHASE")
        self.io.display("="*50 + "\033[0m\n")
        self.io.display("Who do you vote to lynch?")

        targets = [n for n in self.gm.state.alive_characters if n != "Player"] + ["None (Abstain)"]
        for i, target in enumerate(targets):
            self.io.display(f"[{i + 1}] {target}")

        while True:
            try:
                choice = int(self.io.prompt("\n\033[90m[Enter the number of your choice] >\033[0m ")) - 1
                if 0 <= choice < len(targets):
                    selected = targets[choice]
                    return "None" if selected == "None (Abstain)" else selected
                else:
                    self.io.display("\033[91mInvalid choice. Try again.\033[0m")
            except ValueError:
                self.io.display("\033[91mPlease enter a number.\033[0m")

    def get_kill_target(self, valid_targets: list[str]) -> str:
        """Displays a menu for the player werewolf to choose their victim."""
        self.io.display("\n\033[91m" + "="*50)
        self.io.display("                 THE HUNT")
        self.io.display("="*50 + "\033[0m\n")
        self.io.display("Who shall die tonight?")

        for i, target in enumerate(valid_targets):
            self.io.display(f"[{i + 1}] {target}")

        while True:
            try:
                choice = int(self.io.prompt("\n\033[90m[Enter the number of your choice] >\033[0m ")) - 1
                if 0 <= choice < len(valid_targets):
                    return valid_targets[choice]
                else:
                    self.io.display("\033[91mInvalid choice. Try again.\033[0m")
            except ValueError:
                self.io.display("\033[91mPlease enter a number.\033[0m")