from core.game_state import GamePhase
from core.trust_manager import TrustManager


class DiscussionPhase:
    """Handles the main discussion loop: assertions, reactions, and player activity tracking."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state
        config = gm.config

        io.display(f"\n--- PHASE: DISCUSSION (DAY {state.day}) ---")

        max_assertions = config.get("max_assertions_per_day", 8)
        decay_factor = config.get("decay_factor", 0.5)

        assertions_made = 0
        speaker_multipliers = {name: 1.0 for name in state.alive_characters}

        while assertions_made < max_assertions:
            io.display(f"\n--- Assertion {assertions_made + 1}/{max_assertions} ---")
            p_input = io.prompt("[Press Enter to advance, or type to make an assertion] > ")

            speaker_name, assertion_data = self._resolve_speaker(
                p_input, speaker_multipliers, decay_factor, assertions_made
            )

            if speaker_name:
                self._handle_reactions(speaker_name, assertion_data, assertions_made)

            assertions_made += 1

        self._apply_silence_penalty()

        io.display("\n[System]: The sun is setting. Discussion ended.")
        state.player_actions_today = 0
        state.phase = GamePhase.VOTING

    def _resolve_speaker(self, p_input, speaker_multipliers, decay_factor, assertions_made):
        """Determines who speaks this round and returns (speaker_name, assertion_data)."""
        gm = self.gm
        io = gm.io
        state = gm.state

        if p_input.strip():
            parsed_player_data = gm.player_controller.process_input(p_input)
            assertion_data = {
                "dialogue": p_input,
                "intent": parsed_player_data.get("intent", "neutral"),
                "target": parsed_player_data.get("target", "None"),
            }
            return "Player", assertion_data

        speaker_name = gm.npc_controller.calculate_bids(speaker_multipliers)
        assertion_data = gm.npc_controller.generate_assertion(speaker_name, assertions_made)

        if assertion_data:
            dialogue = assertion_data.get("dialogue", "...")
            target = assertion_data.get("target", "None")
            display_target = target if target != "None" else "Room"

            state.chat_history.append(f"[{speaker_name} -> {display_target}]: {dialogue}")
            io.display(f"[{speaker_name} -> {display_target}]: {dialogue}")

        speaker_multipliers[speaker_name] *= decay_factor
        return speaker_name, assertion_data

    def _handle_reactions(self, speaker_name, assertion_data, assertions_made):
        """Manages the reaction loop after someone speaks."""
        gm = self.gm
        io = gm.io

        target = assertion_data.get("target", "None")
        reaction_queue = gm.npc_controller.build_reaction_queue(speaker_name, target)

        player_has_reacted = (speaker_name == "Player")
        player_prompted = (speaker_name == "Player")
        reactions_made = 0

        while reaction_queue or not player_prompted:
            if not player_has_reacted and not player_prompted:
                p_react = io.prompt(f"[Press Enter to advance, or type your reaction to {speaker_name}] > ")
                player_prompted = True

                if p_react.strip():
                    gm.player_controller.process_input(p_react)
                    player_has_reacted = True
                    reactions_made += 1
                    continue
                else:
                    if target == "Player":
                        penalty = -abs(gm.config.get("silence_under_fire_penalty", 8))
                        io.display(
                            "\n\033[91m[System] You refused to defend yourself against a direct claim. "
                            "The town notices your guilt...\033[0m"
                        )
                        TrustManager.apply_global_trust_shift(gm.state, "Player", penalty)

                    if reaction_queue:
                        io.pause("[Press Enter to hear the next reaction] > ")
            else:
                if reaction_queue:
                    io.pause("[Press Enter to hear the next reaction] > ")

            if reaction_queue:
                reactor_name = reaction_queue.pop(0)
                gm.npc_controller.process_reaction(speaker_name, assertion_data, reactor_name, assertions_made)
                reactions_made += 1

        if reactions_made == 0:
            io.display("\n\033[90m[System]: The room remains completely silent.\033[0m")

    def _apply_silence_penalty(self):
        """Penalizes the player if they were too quiet during the day."""
        gm = self.gm
        min_actions = gm.config.get("player_min_actions", 2)
        if gm.state.player_actions_today < min_actions:
            penalty = -abs(gm.config.get("global_trust_penalty", 5))
            gm.io.display("\n\033[91m[System] Your unnatural silence today has bred deep suspicion...\033[0m")
            TrustManager.apply_global_trust_shift(gm.state, "Player", penalty)
