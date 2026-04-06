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

        io.show_phase("DISCUSSION", state.day)

        # Condense previous day's history + morning reports
        if state.day > 0:
            gm.condense_day_history()
            self._morning_reports()

        # Discussion primer — sets the tone and reminds characters of the stakes
        primer = self._build_day_primer()
        io.show_primer(primer)
        state.chat_history.append(f"[Town Crier]: {primer}")

        max_assertions = config.get("max_assertions_per_day", 8)
        decay_factor = config.get("decay_factor", 0.5)

        assertions_made = 0
        speaker_multipliers = {name: 1.0 for name in state.alive_characters}
        prefetched_speaker = None

        while assertions_made < max_assertions:
            io.show_system(f"Assertion {assertions_made + 1}/{max_assertions}", style="muted")
            p_input = io.prompt_assertion()

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

        io.show_system("The sun is setting. Discussion ended.", style="warning")
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
                    io.pause()

    # ------------------------------------------------------------------
    # Assertion helpers
    # ------------------------------------------------------------------

    def _handle_player_assertion(self, p_input):
        """Process player text input and return (speaker_name, assertion_data)."""
        parsed = self.gm.player_controller.process_assertion(p_input)
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
        """Show assertion in the chat window and append to chat history."""
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
                io.show_engine_debug(speaker_name, f"REVEAL as {label}", "Room", "", f"Findings: {findings}")
            else:
                io.show_engine_debug(speaker_name, intent, target, emotion, reasoning)

        if intent == "reveal_role":
            claimed_role = data.get("claimed_role", "")
            label = ROLE_LABELS.get(claimed_role, claimed_role)
            io.show_reveal(speaker_name, label, dialogue)
            state.chat_history.append(f"[{speaker_name} -> Room]: {dialogue}")
        else:
            state.chat_history.append(f"[{speaker_name} -> {display_target}]: {dialogue}")
            io.show_dialogue(speaker_name, display_target, dialogue, intent=intent, emotion=data.get("emotion"))

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
            io.show_engine_debug(reactor_name, intent, target, emotion, reasoning, intensity=intensity)

        io.show_reaction(reactor_name, display_target, dialogue, intent=intent, emotion=data.get("emotion"))

    def _handle_reactions(self, speaker_name, assertion_data, assertions_made, prefetcher):
        """Manages the reaction loop after someone speaks.

        Player can react at any pause point between NPC reactions.
        Prefetches the next NPC reaction while the player reads the current one.
        """
        gm = self.gm
        io = gm.io

        target = assertion_data.get("target", "None")
        assertion_dialogue = assertion_data.get("dialogue", "...")
        reaction_queue = gm.npc_controller.build_reaction_queue(speaker_name, target)

        # Reaction chain: visible only within this assertion round, not in chat_history
        reaction_chain = []  # [{speaker, dialogue, intent}, ...]

        player_has_reacted = (speaker_name == "Player")
        reactions_made = 0
        prefetched_reactor = None

        while reaction_queue:
            # Prompt player before generating the next NPC reaction
            if not player_has_reacted:
                p_react = io.prompt_reaction(speaker_name)
                if p_react.strip():
                    parsed = gm.player_controller.process_reaction(
                        p_react, speaker_name, assertion_dialogue, reaction_chain,
                    )
                    player_has_reacted = True
                    reactions_made += 1
                    reaction_chain.append({
                        "speaker": "Player",
                        "dialogue": p_react,
                        "intent": parsed.get("intent", "neutral"),
                    })
                    prefetcher.invalidate()
                    prefetched_reactor = None
            elif reactions_made > 0:
                io.pause()

            reactor_name = reaction_queue.pop(0)

            # Generate NPC reaction (prefetched or synchronous)
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

            if not reaction_result:
                continue

            self._commit_reaction(reactor_name, reaction_result)
            self._display_reaction(reactor_name, reaction_result)
            reaction_chain.append({
                "speaker": reactor_name,
                "dialogue": reaction_result.get("dialogue", "..."),
                "intent": reaction_result.get("intent", "neutral"),
            })
            reactions_made += 1

            # Prefetch next NPC reaction while player reads this one
            if reaction_queue:
                next_reactor = reaction_queue[0]
                prefetched_reactor = next_reactor
                prefetcher.submit(
                    gm.npc_controller.process_reaction,
                    speaker_name, assertion_data, next_reactor, assertions_made,
                    reaction_chain=reaction_chain,
                )

        # If player was directly targeted and never reacted, give final chance
        if not player_has_reacted and target == "Player":
            p_react = io.prompt_reaction_forced(speaker_name)
            if p_react.strip():
                parsed = gm.player_controller.process_reaction(
                    p_react, speaker_name, assertion_dialogue, reaction_chain,
                )
                reaction_chain.append({
                    "speaker": "Player",
                    "dialogue": p_react,
                    "intent": parsed.get("intent", "neutral"),
                })
                reactions_made += 1
            else:
                penalty = -abs(gm.config.get("silence_under_fire_penalty", 8))
                io.show_system(
                    "You refused to defend yourself against a direct claim. The town notices your guilt...",
                    style="error"
                )
                TrustManager.apply_global_trust_shift(gm.state, "Player", penalty)

        if reactions_made == 0:
            io.show_system("The room remains completely silent.", style="muted")

    # ------------------------------------------------------------------
    # Discussion primer
    # ------------------------------------------------------------------

    def _build_day_primer(self) -> str:
        """Builds a context-setting message for the start of each day's discussion."""
        state = self.gm.state
        alive_count = len(state.alive_characters)
        wolf_warning = "There are werewolves among us. We must find them and vote to lynch them before nightfall, or more will die."

        if state.day == 0:
            return (
                f"Townspeople! {state.main_topic} "
                f"Word has spread that werewolves have infiltrated our village. "
                f"{wolf_warning} "
                f"Speak now — accuse, defend, or question. {alive_count} souls remain."
            )

        # Day 1+: reference last night's events
        killed = state.killed_last_night
        if killed:
            victims = ", ".join(killed)
            return (
                f"Last night, {victims} was found dead — torn apart by werewolves. "
                f"{wolf_warning} "
                f"{alive_count} souls remain. The town must vote today."
            )
        else:
            return (
                f"Miraculously, no one died last night. But the werewolves are still among us. "
                f"{wolf_warning} "
                f"{alive_count} souls remain."
            )

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
                io.show_report(name, label, report)
                state.chat_history.append(f"[{name} ({label} Report)]: {report}")
                state.logical_history.append(
                    f"{name} [morning_report] -> Room. Role: {label}."
                )
                io.pause()

    def _apply_silence_penalty(self):
        """Penalizes the player if they were too quiet during the day."""
        gm = self.gm
        min_actions = gm.config.get("player_min_actions", 2)
        if gm.state.player_actions_today < min_actions:
            penalty = -abs(gm.config.get("global_trust_penalty", 5))
            io = gm.io
            io.show_system("Your unnatural silence today has bred deep suspicion...", style="error")
            TrustManager.apply_global_trust_shift(gm.state, "Player", penalty)
