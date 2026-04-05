from core.game_state import GamePhase
from core.trust_manager import TrustManager
from core.dialogue_cache import DialoguePrefetcher


ROLE_LABELS = {"guardian_angel": "Guardian Angel", "coroner": "Coroner"}


class DiscussionPhase:
    """Handles the main discussion loop: assertions, reactions, and player activity tracking.

    NPC dialogue is generated in the background while the player reads the current
    message. If the player types their own assertion the prefetched result is discarded;
    otherwise it is used immediately, eliminating the wait.
    """

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state
        config = gm.config
        prefetcher = DialoguePrefetcher()

        io.display(f"\n--- PHASE: DISCUSSION (DAY {state.day}) ---")

        # Condense previous day's history + morning reports
        if state.day > 0:
            gm.condense_day_history()
            self._morning_reports()

        max_assertions = config.get("max_assertions_per_day", 8)
        decay_factor = config.get("decay_factor", 0.5)

        assertions_made = 0
        speaker_multipliers = {name: 1.0 for name in state.alive_characters}
        prefetched_speaker = None

        while assertions_made < max_assertions:
            io.display(f"\n--- Assertion {assertions_made + 1}/{max_assertions} ---")
            p_input = io.prompt("[Press Enter to advance, or type to make an assertion] > ")

            if p_input.strip():
                # --- Player speaks: discard any prefetched NPC assertion ---
                prefetcher.invalidate()
                prefetched_speaker = None
                speaker_name, assertion_data = self._handle_player_assertion(p_input)
            elif prefetched_speaker and prefetcher.has_pending():
                # --- Use the prefetched NPC assertion ---
                speaker_name = prefetched_speaker
                assertion_data, _ = prefetcher.get()
                prefetched_speaker = None
                if assertion_data:
                    self._commit_assertion(speaker_name, assertion_data)
                    self._display_assertion(speaker_name, assertion_data)
                speaker_multipliers[speaker_name] *= decay_factor
            else:
                # --- No prefetch available: generate synchronously ---
                prefetched_speaker = None
                speaker_name = gm.npc_controller.calculate_bids(speaker_multipliers)
                assertion_data = gm.npc_controller.generate_assertion(speaker_name, assertions_made)
                if assertion_data:
                    self._commit_assertion(speaker_name, assertion_data)
                    self._display_assertion(speaker_name, assertion_data)
                speaker_multipliers[speaker_name] *= decay_factor

            if speaker_name and assertion_data:
                self._handle_reactions(speaker_name, assertion_data, assertions_made, prefetcher)

            # --- Check for role reveals between assertions ---
            self._check_and_display_reveals()

            assertions_made += 1

            # --- Prefetch the NEXT NPC assertion while player reads reactions ---
            if assertions_made < max_assertions:
                next_speaker = gm.npc_controller.calculate_bids(speaker_multipliers)
                prefetched_speaker = next_speaker
                prefetcher.submit(
                    gm.npc_controller.generate_assertion, next_speaker, assertions_made,
                )

        prefetcher.shutdown()
        self._apply_silence_penalty()

        io.display("\n[System]: The sun is setting. Discussion ended.")
        state.player_actions_today = 0
        state.phase = GamePhase.VOTING

    # ------------------------------------------------------------------
    # Role reveal checks (run between assertion rounds)
    # ------------------------------------------------------------------

    def _check_and_display_reveals(self):
        """Scans all NPCs for pending reveals and injects them between assertions.
        Runs in rounds: each reveal may pressure others, so we rescan until no new reveals fire."""
        gm = self.gm
        io = gm.io

        while True:
            reveals = gm.stat_engine.check_all_reveals()
            if not reveals:
                break
            for name, engine_result in reveals:
                reveal_data = gm.npc_controller.generate_reveal(name, engine_result)
                if reveal_data:
                    self._commit_assertion(name, reveal_data)
                    self._display_assertion(name, reveal_data)
                    io.pause("[Press Enter to continue] > ")

    # ------------------------------------------------------------------
    # Assertion helpers
    # ------------------------------------------------------------------

    def _handle_player_assertion(self, p_input):
        """Process player text input and return (speaker_name, assertion_data)."""
        parsed = self.gm.player_controller.process_input(p_input)
        assertion_data = {
            "dialogue": p_input,
            "intent": parsed.get("intent", "neutral"),
            "target": parsed.get("target", "None"),
        }
        return "Player", assertion_data

    def _commit_assertion(self, speaker_name, data):
        """Apply all state mutations for a committed NPC assertion."""
        gm = self.gm
        state = gm.state
        intent = data["intent"]
        target = data["target"]

        if intent == "reveal_role":
            claimed_role = data["claimed_role"]
            findings = data.get("findings", [])
            label = ROLE_LABELS.get(claimed_role, claimed_role)

            gm.stat_engine.process_duplicate_claim(speaker_name, claimed_role)
            gm.stat_engine.register_reveal(speaker_name, claimed_role)
            gm.stat_engine.apply_reveal_pressure(speaker_name, claimed_role)

            # Record any wolf fake claim
            if data.get("_fake_claim"):
                state.fake_claims.append(data["_fake_claim"])

            state.logical_history.append(
                f"{speaker_name} [reveal_role] -> Room (claimed {label}). Findings: {findings}"
            )
            state.public_events.append(
                f"Day {state.day}: {speaker_name} claimed to be the {label}."
            )
        else:
            emotion = data.get("emotion", "neutral")
            reasoning = data.get("reasoning", "")

            gm.stat_engine.log_action(speaker_name, intent, target)
            state.logical_history.append(
                f"{speaker_name} [{intent}] -> {target} (Emotion: {emotion}). Reason: {reasoning}"
            )
            TrustManager.apply_interaction(state, speaker_name, target, intent, gm.characters)

            # Suspicion updates for public events
            if intent == "deflect" and target == "None":
                gm.stat_engine.update_all_suspicion("deflect_when_accused", source=speaker_name, target="None")
            elif intent == "accuse" and target != "None":
                gm.stat_engine.update_all_suspicion("accusation", source=speaker_name, target=target)

        # Clear reveal pressure after this character has had their chance
        if speaker_name in state.reveal_pressure:
            del state.reveal_pressure[speaker_name]

    def _display_assertion(self, speaker_name, data):
        """Show assertion in the chat window and append to chat history.
        Debug order: engine → weaver → actor dialogue."""
        io = self.gm.io
        state = self.gm.state
        intent = data["intent"]
        dialogue = data.get("dialogue", "...")
        target = data.get("target", "None")
        display_target = target if target != "None" else "Room"

        if self.gm.debug.get("show_logic"):
            emotion = data.get("emotion", "")
            reasoning = data.get("reasoning", "")
            if intent == "reveal_role":
                claimed_role = data.get("claimed_role", "")
                label = ROLE_LABELS.get(claimed_role, claimed_role)
                findings = data.get("findings", [])
                io.display(
                    f"\n\033[93m[Engine ({speaker_name})]: REVEAL as {label} | "
                    f"Findings: {findings}\033[0m"
                )
            else:
                io.display(
                    f"\n\033[90m[Engine ({speaker_name})]: [{intent}] -> {target} "
                    f"({emotion}) | {reasoning}\033[0m"
                )

        if self.gm.debug.get("show_narrative") and data.get("_weaver_debug"):
            io.display(data["_weaver_debug"])

        if intent == "reveal_role":
            io.display(f"\n\033[93m[{speaker_name} -> Room]: {dialogue}\033[0m")
            state.chat_history.append(f"[{speaker_name} -> Room]: {dialogue}")
        else:
            state.chat_history.append(f"[{speaker_name} -> {display_target}]: {dialogue}")
            io.display(f"[{speaker_name} -> {display_target}]: {dialogue}")

    # ------------------------------------------------------------------
    # Reaction helpers
    # ------------------------------------------------------------------

    def _commit_reaction(self, reactor_name, data):
        """Apply state mutations for a committed NPC reaction."""
        gm = self.gm
        state = gm.state
        intent = data["intent"]
        target = data["target"]
        emotion = data.get("emotion", "neutral")
        reasoning = data.get("reasoning", "")
        primary_speaker = data.get("primary_speaker", "")

        gm.stat_engine.log_action(reactor_name, intent, target)
        state.logical_history.append(
            f"{reactor_name} [{intent}] -> {target} (Emotion: {emotion}). Reason: {reasoning}"
        )
        TrustManager.apply_interaction(state, reactor_name, primary_speaker, intent, gm.characters)
        if target != "None" and target != primary_speaker:
            TrustManager.apply_interaction(state, reactor_name, target, intent, gm.characters)

    def _display_reaction(self, reactor_name, data):
        """Show reaction in the chat window. Reactions are NOT added to chat_history —
        they live only in the reaction_chain for this assertion round."""
        io = self.gm.io
        dialogue = data.get("dialogue", "...")
        target = data.get("target", "None")
        intent = data["intent"]
        display_target = target if target != "None" else "Room"

        if self.gm.debug.get("show_logic"):
            emotion = data.get("emotion", "")
            reasoning = data.get("reasoning", "")
            intensity = data.get("intensity", "medium")
            io.display(
                f"\n\033[90m[Engine ({reactor_name})]: [{intent}] -> {target} "
                f"({emotion}, {intensity}) | {reasoning}\033[0m"
            )

        if self.gm.debug.get("show_narrative") and data.get("_weaver_debug"):
            io.display(data["_weaver_debug"])

        io.display(f"[{reactor_name} -> {display_target}]: {dialogue}")

    def _handle_reactions(self, speaker_name, assertion_data, assertions_made, prefetcher):
        """Manages the reaction loop after someone speaks.

        Prefetches the next NPC reaction while the player reads the current one.
        """
        gm = self.gm
        io = gm.io

        target = assertion_data.get("target", "None")
        reaction_queue = gm.npc_controller.build_reaction_queue(speaker_name, target)

        # Reaction chain: visible only within this assertion round, not in chat_history
        reaction_chain = []  # [{speaker, dialogue, intent}, ...]

        player_has_reacted = (speaker_name == "Player")
        player_prompted = (speaker_name == "Player")
        reactions_made = 0
        prefetched_reactor = None

        needs_pause = False  # Only pause before showing the next visible reaction

        while reaction_queue or not player_prompted:
            if not player_has_reacted and not player_prompted:
                p_react = io.prompt(f"[Press Enter to advance, or type your reaction to {speaker_name}] > ")
                player_prompted = True

                if p_react.strip():
                    parsed = gm.player_controller.process_input(p_react)
                    player_has_reacted = True
                    reactions_made += 1
                    needs_pause = True
                    reaction_chain.append({
                        "speaker": "Player",
                        "dialogue": p_react,
                        "intent": parsed.get("intent", "neutral"),
                    })
                    # Invalidate any prefetched reaction (it was built without player context)
                    prefetcher.invalidate()
                    prefetched_reactor = None
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
                reactor_name = reaction_queue.pop(0)

                # Use prefetched reaction if available and matches
                if prefetched_reactor == reactor_name and prefetcher.has_pending():
                    reaction_result, _ = prefetcher.get()
                    prefetched_reactor = None
                else:
                    prefetcher.invalidate()
                    prefetched_reactor = None
                    reaction_result = gm.npc_controller.process_reaction(
                        speaker_name, assertion_data, reactor_name, assertions_made,
                        reaction_chain=reaction_chain,
                    )

                if reaction_result:
                    # Pause before showing this reaction (player reads the previous one)
                    if needs_pause:
                        io.pause("[Press Enter to hear the next reaction] > ")
                    self._commit_reaction(reactor_name, reaction_result)
                    self._display_reaction(reactor_name, reaction_result)
                    reaction_chain.append({
                        "speaker": reactor_name,
                        "dialogue": reaction_result.get("dialogue", "..."),
                        "intent": reaction_result.get("intent", "neutral"),
                    })
                    reactions_made += 1
                    needs_pause = True

                # Prefetch next reaction while player reads this one
                if reaction_queue:
                    next_reactor = reaction_queue[0]
                    prefetched_reactor = next_reactor
                    prefetcher.submit(
                        gm.npc_controller.process_reaction,
                        speaker_name, assertion_data, next_reactor, assertions_made,
                        reaction_chain=reaction_chain,
                    )

        if reactions_made == 0:
            io.display("\n\033[90m[System]: The room remains completely silent.\033[0m")

    # ------------------------------------------------------------------
    # Morning reports & silence penalty
    # ------------------------------------------------------------------

    def _morning_reports(self):
        """Revealed role holders report their findings at the start of each day."""
        gm = self.gm
        io = gm.io
        state = gm.state

        for name in list(state.revealed_roles.keys()):
            if name not in state.alive_characters:
                continue
            if name == "Player":
                continue  # Player reports manually

            report = gm.npc_controller.generate_morning_report(name)
            if report:
                claimed_role = state.revealed_roles[name]
                label = ROLE_LABELS.get(claimed_role, claimed_role)
                io.display(f"\n\033[93m[{name} ({label} Report)]: {report}\033[0m")
                state.chat_history.append(f"[{name} ({label} Report)]: {report}")
                state.logical_history.append(
                    f"{name} [morning_report] -> Room. Role: {label}."
                )
                io.pause("[Press Enter to continue] > ")

    def _apply_silence_penalty(self):
        """Penalizes the player if they were too quiet during the day."""
        gm = self.gm
        min_actions = gm.config.get("player_min_actions", 2)
        if gm.state.player_actions_today < min_actions:
            penalty = -abs(gm.config.get("global_trust_penalty", 5))
            gm.io.display("\n\033[91m[System] Your unnatural silence today has bred deep suspicion...\033[0m")
            TrustManager.apply_global_trust_shift(gm.state, "Player", penalty)
