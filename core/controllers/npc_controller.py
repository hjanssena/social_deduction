import random


class NPCController:
    def __init__(self, gm):
        self.gm = gm

    def calculate_bids(self, multipliers: dict) -> str:
        """Calculates which NPC speaks next."""
        npc_names = [name for name in self.gm.state.alive_characters if name != "Player"]
        if not npc_names:
            return None

        weights = []
        for name in npc_names:
            char_obj = self.gm.characters[name]
            weight = char_obj.assertion_drive * multipliers.get(name, 1.0)
            weights.append(weight)

        chosen_speaker = random.choices(npc_names, weights=weights, k=1)[0]
        return chosen_speaker

    def build_reaction_queue(self, primary_speaker: str, target: str) -> list[str]:
        """Determines which NPCs want to react based on emotional charge."""
        queue = []
        emotional_threshold = 10

        if target in self.gm.state.alive_characters and target != primary_speaker and target != "Player":
            queue.append(target)

        potential_reactors = [n for n in self.gm.state.alive_characters
                              if n not in queue and n != primary_speaker and n != "Player"]

        npc_scores = {}
        for npc in potential_reactors:
            trust_speaker = self.gm.state.trust_matrix[npc].get(primary_speaker, 50)
            charge_speaker = abs(trust_speaker - 50)

            charge_target = 0
            if target in self.gm.state.alive_characters:
                trust_target = self.gm.state.trust_matrix[npc].get(target, 50)
                charge_target = abs(trust_target - 50)

            max_charge = max(charge_speaker, charge_target)
            if max_charge >= emotional_threshold:
                npc_scores[npc] = max_charge

        sorted_bystanders = sorted(npc_scores, key=npc_scores.get, reverse=True)
        queue.extend(sorted_bystanders)
        return queue

    # ================================================================
    # REVEAL PIPELINE (called between assertions, not from bids)
    # ================================================================

    def generate_reveal(self, speaker_name: str, engine_result: dict) -> dict:
        """Generates LLM dialogue for a reveal. Called with the engine result from check_all_reveals."""
        char_obj = self.gm.characters[speaker_name]
        role = self.gm.state.roles.get(speaker_name, "villager")
        return self._handle_role_reveal(speaker_name, char_obj, role, engine_result)

    # ================================================================
    # ASSERTION PIPELINE: StatEngine → single LLM call (reasoning + dialogue)
    # ================================================================

    def generate_assertion(self, speaker_name: str, current_assertion: int) -> dict:
        """Pure generation — no state mutations, no display. Caller applies side effects."""
        char_obj = self.gm.characters[speaker_name]
        role = self.gm.state.roles.get(speaker_name, "villager")

        # --- STEP 1: StatEngine ---
        engine_result = self.gm.stat_engine.compute_assertion(speaker_name)
        intent = engine_result["intent"]
        target = engine_result["target"]
        emotion = engine_result["emotion"]
        engine_reasoning = engine_result["engine_reasoning"]

        # --- STEP 2: Single LLM call (reasoning → dialogue) ---
        werewolves = [name for name, r in self.gm.state.roles.items() if r == "werewolf"]
        coroner_knowledge = self.gm.state.coroner_knowledge if role == "coroner" else None
        ga_history = self.gm.state.ga_protection_history if role == "guardian_angel" else None
        system = self.gm.prompt_builder.build_system_prompt(
            char_obj, role, known_werewolves=werewolves,
            coroner_knowledge=coroner_knowledge, ga_protection_history=ga_history,
        )
        prompt = self.gm.prompt_builder.build_assertion_prompt(
            character_name=speaker_name,
            intent=intent,
            target=target,
            emotion=emotion,
            engine_reasoning=engine_reasoning,
            chat_history=self.gm.state.chat_history,
            main_topic=self.gm.state.main_topic,
            roster_text=self.gm.get_roster_text(viewer=speaker_name),
            character=char_obj,
            claims_text=self.gm.get_claims_text(),
            game_context=self.gm.get_game_context(),
        )
        
        data = self.gm.llm.generate_json(system, prompt, True)
        #print(data)
        raw_dialogue = data.get("dialogue", "... (Glares in silence)") if data else "... (Glares in silence)"

        return {
            "dialogue": raw_dialogue,
            "intent": intent,
            "target": target,
            "emotion": emotion,
            "reasoning": engine_reasoning,
        }

    # ================================================================
    # REACTION PIPELINE: StatEngine → single LLM call (reasoning + dialogue)
    # ================================================================

    def process_reaction(self, primary_speaker: str, assertion_data: dict,
                         reactor_name: str, current_assertion: int,
                         reaction_chain: list = None):
        """Pure generation — no state mutations, no display. Caller applies side effects.

        Args:
            primary_speaker: The original asserter's name.
            assertion_data: The original assertion that started this reaction chain.
            reactor_name: Who is reacting.
            current_assertion: Index of current assertion round.
            reaction_chain: List of {speaker, dialogue, intent} dicts for reactions so far.
        """
        reactor_obj = self.gm.characters[reactor_name]
        role = self.gm.state.roles.get(reactor_name, "villager")

        # Engine ALWAYS reasons about the original assertion
        speaker_intent = assertion_data.get("intent", "neutral")
        speaker_target = assertion_data.get("target", "None")
        speaker_dialogue = assertion_data.get("dialogue", "...")

        # --- STEP 1: StatEngine ---
        engine_result = self.gm.stat_engine.compute_reaction(
            reactor_name, primary_speaker, speaker_intent, speaker_target
        )
        if engine_result is None:
            return None

        intent = engine_result["intent"]
        target = engine_result["target"]
        emotion = engine_result["emotion"]
        engine_reasoning = engine_result["engine_reasoning"]
        intensity = engine_result.get("intensity", "medium")

        # --- STEP 2: Single LLM call (reasoning → dialogue) ---
        chain = reaction_chain or []
        werewolves = [name for name, r in self.gm.state.roles.items() if r == "werewolf"]
        coroner_knowledge = self.gm.state.coroner_knowledge if role == "coroner" else None
        ga_history = self.gm.state.ga_protection_history if role == "guardian_angel" else None
        system = self.gm.prompt_builder.build_system_prompt(
            reactor_obj, role, known_werewolves=werewolves,
            coroner_knowledge=coroner_knowledge, ga_protection_history=ga_history,
        )
        prompt = self.gm.prompt_builder.build_reaction_prompt(
            character_name=reactor_name,
            intent=intent,
            target=target,
            emotion=emotion,
            engine_reasoning=engine_reasoning,
            assertion_speaker=primary_speaker,
            assertion_dialogue=speaker_dialogue,
            reaction_chain=chain,
            main_topic=self.gm.state.main_topic,
            roster_text=self.gm.get_roster_text(viewer=reactor_name),
            character=reactor_obj,
            claims_text=self.gm.get_claims_text(),
            game_context=self.gm.get_game_context(),
        )
        data = self.gm.llm.generate_json(system, prompt, True)
        raw_dialogue = data.get("dialogue", "... (Glares in silence)") if data else "... (Glares in silence)"
        # print(data)
        # raw_dialogue = self.gm.llm.generate_text(system, prompt)
        # if not raw_dialogue or raw_dialogue.isspace():
        #     raw_dialogue = "... (Glares in silence)"

        return {
            "dialogue": raw_dialogue.strip().strip('"'),
            "intent": intent,
            "target": target,
            "emotion": emotion,
            "reasoning": engine_reasoning,
            "primary_speaker": primary_speaker,
            "intensity": intensity,
        }

    # ================================================================
    # ROLE REVEALS & MORNING REPORTS
    # ================================================================

    def _handle_role_reveal(self, speaker_name: str, char_obj, role: str, engine_result: dict) -> dict:
        """Pure generation for role reveals — no state mutations."""
        claimed_role = engine_result["claimed_role"]
        findings = engine_result.get("findings", [])
        is_pressure = engine_result.get("intensity") == "high" and "counter" in engine_result.get("engine_reasoning", "")

        ROLE_LABELS = {"guardian_angel": "Guardian Angel", "coroner": "Coroner"}
        label = ROLE_LABELS.get(claimed_role, claimed_role)

        # Build system prompt (role-aware so the actor knows if they're lying)
        werewolves = [name for name, r in self.gm.state.roles.items() if r == "werewolf"]
        system_prompt = self.gm.prompt_builder.build_system_prompt(
            char_obj, role, known_werewolves=werewolves,
        )

        reveal_prompt = self.gm.prompt_builder.build_role_reveal_prompt(
            character_name=speaker_name,
            claimed_role=claimed_role,
            findings=findings,
            chat_history=self.gm.state.chat_history,
            is_pressure=is_pressure,
            character=char_obj,
        )

        reveal_data = self.gm.llm.generate_json(system_prompt, reveal_prompt, use_narrative_cfg=True)
        raw_dialogue = reveal_data.get("dialogue", f"I am the {label}.") if reveal_data else f"I am the {label}."

        return {
            "dialogue": raw_dialogue,
            "intent": "reveal_role",
            "target": "None",
            "emotion": engine_result.get("emotion", "arrogant"),
            "reasoning": engine_result["engine_reasoning"],
            "claimed_role": claimed_role,
            "findings": findings,
            "_fake_claim": engine_result.get("_fake_claim"),
        }

    def generate_morning_report(self, speaker_name: str) -> str | None:
        """Generates a morning report for a revealed role holder. Returns dialogue or None."""
        char_obj = self.gm.characters.get(speaker_name)
        if not char_obj:
            return None

        claimed_role = self.gm.state.revealed_roles.get(speaker_name)
        if not claimed_role:
            return None

        real_role = self.gm.state.roles.get(speaker_name, "villager")

        # Determine new findings since last report
        if real_role == claimed_role:
            # Real role holder: share actual new findings
            new_findings = self._get_new_findings(speaker_name, real_role)
        elif real_role == "werewolf":
            # Fake claim: fabricate findings
            new_findings = self.gm.stat_engine._fabricate_findings(speaker_name, claimed_role)
        else:
            return None

        if not new_findings:
            return None

        werewolves = [name for name, r in self.gm.state.roles.items() if r == "werewolf"]
        system_prompt = self.gm.prompt_builder.build_system_prompt(
            char_obj, real_role, known_werewolves=werewolves if real_role == "werewolf" else None,
        )

        report_prompt = self.gm.prompt_builder.build_morning_report_prompt(
            character_name=speaker_name,
            claimed_role=claimed_role,
            new_findings=new_findings,
            chat_history=self.gm.state.chat_history,
            character=char_obj,
        )

        report_data = self.gm.llm.generate_json(system_prompt, report_prompt, use_narrative_cfg=True)
        dialogue = report_data.get("dialogue") if report_data else None
        return dialogue

    def _get_new_findings(self, name: str, role: str) -> list[str]:
        """Gets findings from the most recent night only."""
        day = self.gm.state.day
        if role == "guardian_angel":
            return [f for f in self.gm.state.ga_protection_history if f.startswith(f"Night {day - 1}")]
        elif role == "coroner":
            return [f for f in self.gm.state.coroner_knowledge if f.startswith(f"Day {day - 1}")]
        return []

    # ================================================================
    # VOTING — StatEngine only, no LLM
    # ================================================================

    def generate_vote(self, voter_name: str) -> dict:
        return self.gm.stat_engine.compute_vote(voter_name)

    # ================================================================
    # NIGHT ACTIONS — StatEngine only, no LLM
    # ================================================================

    def generate_kill_preference(self, werewolf_name: str, valid_targets: list[str]) -> dict:
        return self.gm.stat_engine.compute_kill_preference(werewolf_name, valid_targets)

    def generate_wolf_whisper(self, werewolf_name: str, valid_targets: list[str]) -> dict:
        """Generates an in-character whisper from a fellow werewolf about who to kill."""
        char_obj = self.gm.characters[werewolf_name]
        werewolves = [name for name, r in self.gm.state.roles.items() if r == "werewolf"]

        # Step 1: StatEngine picks the target
        pref = self.gm.stat_engine.compute_kill_preference(werewolf_name, valid_targets)
        target = pref["target"]
        engine_reasoning = pref["thought_process"]

        # Step 2: LLM generates in-character whisper
        system_prompt = self.gm.prompt_builder.build_system_prompt(
            char_obj, "werewolf", known_werewolves=werewolves,
        )
        whisper_prompt = self.gm.prompt_builder.build_wolf_whisper_prompt(
            speaker_name=werewolf_name,
            occupation=char_obj.occupation,
            target=target,
            engine_reasoning=engine_reasoning,
            valid_targets=valid_targets,
            chat_history=self.gm.state.chat_history,
            character=char_obj,
        )

        whisper_data = self.gm.llm.generate_json(system_prompt, whisper_prompt, use_narrative_cfg=True)
        dialogue = whisper_data.get("dialogue", engine_reasoning) if whisper_data else engine_reasoning

        return {"target": target, "thought_process": engine_reasoning, "dialogue": dialogue}

    def generate_protect_preference(self, ga_name: str, valid_targets: list[str]) -> dict:
        return self.gm.stat_engine.compute_protect_preference(ga_name, valid_targets)

    # ================================================================
    # FINAL WORDS — kept as LLM call (emotional impact)
    # ================================================================

    def generate_final_words(self, character_name: str) -> str:
        char_obj = self.gm.characters[character_name]
        role = self.gm.state.roles.get(character_name, "villager")
        werewolves = [name for name, r in self.gm.state.roles.items() if r == "werewolf"]
        coroner_knowledge = self.gm.state.coroner_knowledge if role == "coroner" else None
        ga_history = self.gm.state.ga_protection_history if role == "guardian_angel" else None
        system_prompt = self.gm.prompt_builder.build_system_prompt(
            char_obj, role, known_werewolves=werewolves,
            coroner_knowledge=coroner_knowledge, ga_protection_history=ga_history,
        )

        user_prompt = self.gm.prompt_builder.build_final_words_prompt(
            character_name=character_name,
            secret_role=role,
            alive_characters=self.gm.state.alive_characters,
            chat_history=self.gm.state.chat_history,
            character=char_obj,
        )

        dialogue = self.gm.llm.generate_text(system_prompt, user_prompt)
        return dialogue if dialogue else "..."
