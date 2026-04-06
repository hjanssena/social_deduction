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

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_and_validate(self, parsed_data: dict) -> dict:
        """Validate intent and sanitize target from raw LLM parse output."""
        raw_target = parsed_data.get("target", "None")
        safe_target = self.gm.sanitize_target(raw_target)

        if raw_target != "None" and safe_target == "None":
            self.io.show_system(f"LLM hallucinated target '{raw_target}'. Defaulting to 'None'.", style="warning")

        parsed_data["target"] = safe_target

        if parsed_data.get("intent") not in VALID_INTENTS.split("|"):
            self.io.show_system(f"Invalid intent '{parsed_data.get('intent')}'. Defaulting to 'neutral'.", style="warning")
            parsed_data["intent"] = "neutral"

        return parsed_data

    def _apply_trust_and_log(self, intent: str, target: str, emotion: str, summary: str):
        """Shared trust + logical_history update for both assertions and reactions."""
        TrustManager.apply_interaction(
            game_state=self.gm.state,
            source="Player",
            target=target,
            intent=intent,
            characters_dict=self.gm.characters
        )
        self.gm.state.logical_history.append(
            f"Player [{intent}] -> {target} (Emotion: {emotion}). Reason: {summary}"
        )

    # ------------------------------------------------------------------
    # Assertion processing
    # ------------------------------------------------------------------

    def process_assertion(self, player_text: str) -> dict:
        """Parse player assertion, apply trust, add to chat_history."""
        self.gm.state.player_actions_today += 1
        self._check_domination_penalty()

        roster_text = self.gm.get_roster_text(viewer="Player")
        self.io.show_system("Parsing...", style="muted")

        system_prompt = self.gm.prompt_builder.build_assertion_parser_prompt(
            player_text=player_text,
            roster_text=roster_text,
            chat_history=self.gm.state.chat_history,
        )
        parsed_data = self._parse_and_validate(
            self.gm.llm.generate_json(system_prompt, "Parse the player's text.")
        )

        intent = parsed_data.get("intent", "neutral")
        target = parsed_data.get("target", "None")
        emotion = parsed_data.get("emotion", "neutral")
        summary = parsed_data.get("summary", "Spoke to the room.")

        self._apply_trust_and_log(intent, target, emotion, summary)

        display_target = target if target != "None" else "Room"
        self.gm.state.chat_history.append(f"[Player -> {display_target}]: {player_text}")

        return parsed_data

    # ------------------------------------------------------------------
    # Reaction processing
    # ------------------------------------------------------------------

    def process_reaction(self, player_text: str, assertion_speaker: str,
                         assertion_dialogue: str, reaction_chain: list[dict]) -> dict:
        """Parse player reaction, apply trust. Does NOT add to chat_history."""
        self.gm.state.player_actions_today += 1
        self._check_domination_penalty()

        roster_text = self.gm.get_roster_text(viewer="Player")
        self.io.show_system("Parsing...", style="muted")

        system_prompt = self.gm.prompt_builder.build_reaction_parser_prompt(
            player_text=player_text,
            roster_text=roster_text,
            assertion_speaker=assertion_speaker,
            assertion_dialogue=assertion_dialogue,
            reaction_chain=reaction_chain,
        )
        parsed_data = self._parse_and_validate(
            self.gm.llm.generate_json(system_prompt, "Parse the player's text.")
        )

        intent = parsed_data.get("intent", "neutral")
        target = parsed_data.get("target", "None")
        emotion = parsed_data.get("emotion", "neutral")
        summary = parsed_data.get("summary", "Reacted.")

        self._apply_trust_and_log(intent, target, emotion, summary)

        return parsed_data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_domination_penalty(self):
        """Apply penalty if player is speaking too much."""
        max_actions = self.gm.config.get("player_max_actions", 4)
        if self.gm.state.player_actions_today > max_actions:
            penalty = -abs(self.gm.config.get("global_trust_penalty", 5))
            self.io.show_system("The town grows highly suspicious of your constant interjections...", style="error")
            TrustManager.apply_global_trust_shift(self.gm.state, "Player", penalty)

    def get_vote(self) -> str:
        """Displays a menu for the player to cast their vote."""
        targets = [n for n in self.gm.state.alive_characters if n != "Player"] + ["Abstain"]
        choice = self.io.prompt_menu("Who do you vote to lynch?", targets, context="vote")
        selected = targets[choice]
        return "None" if selected == "Abstain" else selected

    def get_kill_target(self, valid_targets: list[str]) -> str:
        """Displays a menu for the player werewolf to choose their victim."""
        choice = self.io.prompt_menu("Who shall die tonight?", valid_targets, context="kill")
        return valid_targets[choice]
