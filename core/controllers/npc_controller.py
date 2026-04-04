from core.trust_manager import TrustManager
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
        
        # bids_debug = {name: round(weight, 2) for name, weight in zip(npc_names, weights)}
        # print(f"\n[Bidding System] Live Weights: {bids_debug} -> Winner: {chosen_speaker}")
        return chosen_speaker

    def build_reaction_queue(self, primary_speaker: str, target: str) -> list[str]:
        """Determines which NPCs want to react based on emotional charge."""
        queue = []
        emotional_threshold = 20 
        
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

    def generate_assertion(self, speaker_name: str, current_assertion: int) -> dict:
        char_obj = self.gm.characters[speaker_name]
        role = self.gm.state.roles.get(speaker_name, "villager")
        werewolves = [name for name, r in self.gm.state.roles.items() if r == "werewolf"]
        system_prompt = self.gm.prompt_builder.build_system_prompt(char_obj, role, known_werewolves=werewolves)
        
        relationship_text = TrustManager.get_all_relationships_prompt(speaker_name, self.gm.state)
        player_status = self.gm.player_controller.get_status(current_assertion)
        roster_text = self.gm.get_roster_text()
        
        main_topic = self.gm.state.main_topic

        # --- PHASE 1: LOGIC ---
        logic_prompt = self.gm.prompt_builder.build_logic_prompt(
            logical_history=self.gm.state.logical_history, # Uses Logic Track
            alive_characters=self.gm.state.alive_characters,
            public_events=self.gm.state.public_events,
            main_topic=main_topic,
            speaker_name=speaker_name,
            window_size=self.gm.config.get("chat_history_window", 5),
            relationship_context=relationship_text,
            player_status=player_status,
            roster_text=roster_text
        )
        
        logic_data = self.gm.llm.generate_json(system_prompt, logic_prompt)
        
        if not logic_data:
            return None
            
        situation = logic_data.get("situation_analysis", "")
        strategy = logic_data.get("strategic_thought", "")
        intent = logic_data.get("intent", "neutral")
        safe_target = self.gm.sanitize_target(logic_data.get("target", "None"))
        emotion = logic_data.get("emotion", "neutral")
        reasoning = logic_data.get("reasoning", "No reason given.")

        print(f"\n\033[90m[Brain ({speaker_name})]: {situation} {strategy} -> [{intent} {safe_target} ({emotion})]\033[0m")

        # Update Logic Track & Apply Trust
        self.gm.state.logical_history.append(f"{speaker_name} [{intent}] -> {safe_target} (Emotion: {emotion}). Reason: {reasoning}")
        TrustManager.apply_interaction(self.gm.state, speaker_name, safe_target, intent, self.gm.characters)

        # --- PHASE 2: NARRATIVE ---
        narrative_prompt = self.gm.prompt_builder.build_narrative_prompt(
            speaker_name=speaker_name,
            intent=intent,
            target=safe_target,
            emotion=emotion,
            reasoning=reasoning,
            chat_history=self.gm.state.chat_history,
            main_topic=main_topic,
            public_events=self.gm.state.public_events,
            roster_text=roster_text,
            character=char_obj
        )

        narrative_data = self.gm.llm.generate_json(system_prompt, narrative_prompt, use_narrative_cfg=True)
        raw_dialogue = narrative_data.get("dialogue", "... (Glares in silence)")

        # Package it up to send back to GameMaster
        return {
            "dialogue": raw_dialogue,
            "intent": intent,
            "target": safe_target,
            "emotion": emotion,
            "reasoning": reasoning
        }

    def process_reaction(self, primary_speaker: str, assertion_data: dict, reactor_name: str, current_assertion: int):
        reactor_obj = self.gm.characters[reactor_name]
        role = self.gm.state.roles.get(reactor_name, "villager")
        werewolves = [name for name, r in self.gm.state.roles.items() if r == "werewolf"]
        system_prompt = self.gm.prompt_builder.build_system_prompt(reactor_obj, role, known_werewolves=werewolves)
        
        # Build the Logical Event Context so the Brain knows what it's reacting to
        logical_event = f"{primary_speaker} [{assertion_data.get('intent')}] -> {assertion_data.get('target')} (Emotion: {assertion_data.get('emotion')})"
        
        relationship_text = f"Regarding {primary_speaker}: " + TrustManager.get_relationship_prompt(self.gm.state.trust_matrix[reactor_name].get(primary_speaker, 50))
        
        # --- PHASE 1: LOGIC ---
        logic_prompt = self.gm.prompt_builder.build_logic_prompt(
            logical_history=self.gm.state.logical_history,
            alive_characters=self.gm.state.alive_characters,
            public_events=self.gm.state.public_events,
            main_topic=self.gm.state.main_topic,
            speaker_name=reactor_name,
            window_size=self.gm.config.get("chat_history_window", 5),
            current_event=logical_event,
            relationship_context=relationship_text,
            player_status=self.gm.player_controller.get_status(current_assertion),
            roster_text=self.gm.get_roster_text()
        )
        
        logic_data = self.gm.llm.generate_json(system_prompt, logic_prompt)

        if not logic_data:
            print(f"\033[90m[Brain ({reactor_name})]: ... (no response)\033[0m")
            return

        situation = logic_data.get("situation_analysis", "")
        strategy = logic_data.get("strategic_thought", "")
        intent = logic_data.get("intent", "neutral")
        safe_target = self.gm.sanitize_target(logic_data.get("target", "None"))
        emotion = logic_data.get("emotion", "neutral")
        reasoning = logic_data.get("reasoning", "No reason given.")

        print(f"\033[90m[Brain ({reactor_name})]: {situation} {strategy} -> [{intent} {safe_target} ({emotion})]\033[0m")

        # Update Logic Track & Apply Trust
        self.gm.state.logical_history.append(f"{reactor_name} [{intent}] -> {safe_target} (Emotion: {emotion}). Reason: {reasoning}")
        TrustManager.apply_interaction(self.gm.state, reactor_name, primary_speaker, intent, self.gm.characters)
        if safe_target != "None" and safe_target != primary_speaker:
            TrustManager.apply_interaction(self.gm.state, reactor_name, safe_target, intent, self.gm.characters)

        # --- PHASE 2: NARRATIVE ---
        narrative_prompt = self.gm.prompt_builder.build_narrative_prompt(
            speaker_name=reactor_name,
            intent=intent,
            target=safe_target,
            emotion=emotion,
            reasoning=reasoning,
            chat_history=self.gm.state.chat_history,
            main_topic=self.gm.state.main_topic,
            public_events=self.gm.state.public_events,
            roster_text=self.gm.get_roster_text(),
            character=reactor_obj
        )

        narrative_data = self.gm.llm.generate_json(system_prompt, narrative_prompt, use_narrative_cfg=True)
        raw_dialogue = narrative_data.get("dialogue", "... (Glares in silence)")

        display_target = safe_target if safe_target != "None" else "Room"
        self.gm.state.chat_history.append(f"[{reactor_name} -> {display_target}]: {raw_dialogue}")
        print(f"[{reactor_name} -> {display_target}]: {raw_dialogue}")

    def generate_vote(self, voter_name: str) -> dict:
        """Quietly asks the LLM who this NPC wants to vote for."""
        role = self.gm.state.roles.get(voter_name, "villager")
        
        # --- GET PACK LIST ---
        werewolves = [name for name, r in self.gm.state.roles.items() if r == "werewolf"]
        system_prompt = self.gm.prompt_builder.build_system_prompt(self.gm.characters[voter_name], secret_role=role, known_werewolves=werewolves)
        
        relationship_text = TrustManager.get_all_relationships_prompt(voter_name, self.gm.state)
        roster_text = self.gm.get_roster_text()
        user_prompt = self.gm.prompt_builder.build_voting_prompt(
            character_name=voter_name,
            alive_characters=self.gm.state.alive_characters,
            chat_history=self.gm.state.chat_history,
            public_events=self.gm.state.public_events,
            relationship_context= relationship_text,
            roster_text= roster_text,
            secret_role=role
        )
        
        # Notice we are not printing "Generating..." here so we don't interrupt the player's menu
        vote_data = self.gm.llm.generate_json(system_prompt, user_prompt)
        
        if vote_data:
            safe_target = self.gm.sanitize_target(vote_data.get("target", "None"))
            vote_data["target"] = safe_target
            return vote_data
            
        return {"thought_process": "Error processing logic.", "target": "None"}
    

    def generate_kill_preference(self, werewolf_name: str, valid_targets: list[str]) -> dict:
        """Asks an NPC werewolf who they want to murder."""
        char_obj = self.gm.characters[werewolf_name]
        role = "werewolf"
        
        # The pack knows each other
        werewolves = [name for name, r in self.gm.state.roles.items() if r == "werewolf"]
        system_prompt = self.gm.prompt_builder.build_system_prompt(char_obj, role, known_werewolves=werewolves)
        
        relationship_text = TrustManager.get_all_relationships_prompt(werewolf_name, self.gm.state)
        
        user_prompt = self.gm.prompt_builder.build_night_action_prompt(
            character_name=werewolf_name,
            valid_targets=valid_targets,
            logical_history=self.gm.state.logical_history,
            relationship_context=relationship_text
        )
        
        # We use the Cold Brain (generate_json) because this is a strict tactical choice
        action_data = self.gm.llm.generate_json(system_prompt, user_prompt)
        
        if action_data:
            safe_target = self.gm.sanitize_target(action_data.get("target", "None"))
            if safe_target not in valid_targets:
                safe_target = random.choice(valid_targets) if valid_targets else "None"
            action_data["target"] = safe_target
            return action_data

        return {"thought_process": "I thirst for blood.", "target": random.choice(valid_targets) if valid_targets else "None"}

    def generate_final_words(self, character_name: str) -> str:
        """Generates a condemned NPC's last words before execution."""
        char_obj = self.gm.characters[character_name]
        role = self.gm.state.roles.get(character_name, "villager")
        werewolves = [name for name, r in self.gm.state.roles.items() if r == "werewolf"]
        system_prompt = self.gm.prompt_builder.build_system_prompt(char_obj, role, known_werewolves=werewolves)

        user_prompt = self.gm.prompt_builder.build_final_words_prompt(
            character_name=character_name,
            secret_role=role,
            alive_characters=self.gm.state.alive_characters,
            chat_history=self.gm.state.chat_history,
            character=char_obj
        )

        dialogue = self.gm.llm.generate_text(system_prompt, user_prompt)
        return dialogue if dialogue else "..."