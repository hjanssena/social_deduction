from core.game_state import GameState, GamePhase
from core.trust_manager import TrustManager
import random

class GameMaster:
    def __init__(self, llm_service, prompt_service, characters):
        self.llm = llm_service
        self.prompt_builder = prompt_service
        self.characters = {c.name: c for c in characters}
        
        # Initialize the state machine
        self.state = GameState(characters)

    def run_loop(self):
        """The main execution loop that routes to specific phase handlers."""
        print("Starting Game Loop...")
        
        while self.state.phase != GamePhase.GAME_OVER:
            if self.state.phase == GamePhase.PROLOGUE:
                self.handle_prologue()
            
            elif self.state.phase == GamePhase.DISCUSSION:
                self.handle_discussion_phase()
                
            elif self.state.phase == GamePhase.VOTING:
                self.handle_voting_phase()
                
            elif self.state.phase == GamePhase.NIGHT:
                self.handle_night_phase()
                
            else:
                print(f"Phase {self.state.phase} not implemented yet.")
                break # Break to avoid infinite loops during skeleton testing

    def handle_prologue(self):
        """Day 0 introduction."""
        print("\n--- PHASE: PROLOGUE ---")
        # TODO: Implement Mayor's opening statement
        
        # Transition to next state
        self.state.phase = GamePhase.DISCUSSION 

    def handle_discussion_phase(self):
        """
        A fast-paced debate capped by max assertions.
        Uses Enter to advance dialogue, or typed text to interrupt.
        """
        print(f"\n--- PHASE: DISCUSSION (DAY {self.state.day}) ---")
        
        # In a real app, load these from config.json
        max_assertions = 8 
        decay_factor = 0.5 
        
        assertions_made = 0
        speaker_multipliers = {name: 1.0 for name in self.state.alive_characters}

        while assertions_made < max_assertions:
            # ---------------------------------------------------------
            # 1. THE ASSERTION SLOT
            # ---------------------------------------------------------
            print(f"\n--- Assertion {assertions_made + 1}/{max_assertions} ---")
            p_input = input("[Press Enter to advance, or type to make an assertion] > ")
            
            if p_input.strip():
                # Player interrupted and took the assertion slot
                speaker_name = "Player"
                self.process_player_input(p_input)
                assertion_data = {"dialogue": p_input} # Mock data for the reaction context
            else:
                # Player passed, let the NPCs bid and assert
                speaker_name = self._calculate_bids(speaker_multipliers)
                assertion_data = self._generate_assertion(speaker_name)
                
                if assertion_data:
                    dialogue = assertion_data.get('dialogue', '...')
                    self.state.chat_history.append(f"[{speaker_name}]: {dialogue}")
                    print(f"[{speaker_name}]: {dialogue}")
                
                # Apply decay penalty
                speaker_multipliers[speaker_name] *= decay_factor

            # ---------------------------------------------------------
            # 2. THE REACTION SLOT
            # ---------------------------------------------------------
            if speaker_name:
                if speaker_name != "Player":
                    # Let the player react to the NPC, or press Enter to let another NPC react
                    p_react = input(f"\n[Press Enter to advance, or type your reaction to {speaker_name}] > ")
                    if p_react.strip():
                        # Player took the one reaction slot for this round
                        self.process_player_input(p_react)
                    else:
                        # Player passed, generate an NPC reaction
                        self._process_reactions_to_assertion(speaker_name, assertion_data)
                else:
                    # The Player made the assertion. Wait for them to hit Enter before generating the NPC's reaction.
                    input("\n[Press Enter to see how the town reacts to you] > ")
                    self._process_reactions_to_assertion("Player", assertion_data)

            assertions_made += 1

        print("\n[System]: The sun is setting. Discussion ended.")
        self.state.phase = GamePhase.VOTING

    def _calculate_bids(self, multipliers: dict) -> str:
        """
        Calculates which NPC speaks next based on their assertion_drive and current multiplier.
        Returns the name of the winning character.
        """
        # Filter out the Player and any dead characters
        npc_names = [name for name in self.state.alive_characters if name != "Player"]
        
        if not npc_names:
            return None
            
        weights = []
        for name in npc_names:
            char_obj = self.characters[name]
            # Formula: (Base Drive) * (Current Multiplier)
            weight = char_obj.assertion_drive * multipliers.get(name, 1.0)
            weights.append(weight)
            
        # Select the winner based on the calculated probability weights
        chosen_speaker = random.choices(npc_names, weights=weights, k=1)[0]
        
        # --- Debugging Output to see the math in action ---
        bids_debug = {name: round(weight, 2) for name, weight in zip(npc_names, weights)}
        print(f"\n[Bidding System] Live Weights: {bids_debug} -> Winner: {chosen_speaker}")
        
        return chosen_speaker

    def _generate_assertion(self, speaker_name: str) -> dict:
        """Generates the primary assertion, aware of the last 5 messages."""
        char_obj = self.characters[speaker_name]
        system_prompt = self.prompt_builder.build_system_prompt(char_obj)
        
        user_prompt = self.prompt_builder.build_discussion_prompt(
            chat_history=self.state.chat_history,
            alive_characters=self.state.alive_characters,
            public_events=self.state.public_events # Passed here
        )
        
        print(f"--- Generating Assertion for {speaker_name} ---")
        assertion_data = self.llm.generate_json(system_prompt, user_prompt)
        
        if assertion_data:
            TrustManager.apply_interaction(
                game_state=self.state,
                source=speaker_name,
                target=assertion_data.get("target", "None"),
                intent=assertion_data.get("intent", "neutral"),
                characters_dict=self.characters
            )
            
        return assertion_data

    def _process_reactions_to_assertion(self, primary_speaker: str, assertion_data: dict):
        """Generates a reaction, fully aware of the last 5 messages AND the immediate event."""
        potential_reactors = [name for name in self.state.alive_characters 
                              if name != primary_speaker and name != "Player"]
        
        if not potential_reactors:
            return

        import random
        reactor_name = random.choice(potential_reactors)
        reactor_obj = self.characters[reactor_name]
        
        system_prompt = self.prompt_builder.build_system_prompt(reactor_obj)
        event_context = f"[{primary_speaker}]: {assertion_data.get('dialogue')}"
        
        # We pass BOTH the chat history AND the specific event they need to react to
        user_prompt = self.prompt_builder.build_discussion_prompt(
            chat_history=self.state.chat_history,
            alive_characters=self.state.alive_characters,
            public_events=self.state.public_events, # Passed here
            current_event=event_context
        )
        
        print(f"--- Generating Reaction for {reactor_name} ---")
        reaction_data = self.llm.generate_json(system_prompt, user_prompt)
        
        if reaction_data:
            self.state.chat_history.append(f"[{reactor_name}]: {reaction_data.get('dialogue')}")
            print(f"[{reactor_name}]: {reaction_data.get('dialogue')}")
            
            # 1. Update trust towards the Primary Speaker (e.g., disagreeing with them lowers trust)
            TrustManager.apply_interaction(
                game_state=self.state,
                source=reactor_name,
                target=primary_speaker,
                intent=reaction_data.get("intent", "neutral"),
                characters_dict=self.characters
            )
            
            # 2. Update trust towards the actual Target mentioned in the JSON (if it's someone else)
            target = reaction_data.get("target", "None")
            if target != "None" and target != primary_speaker:
                TrustManager.apply_interaction(
                    game_state=self.state,
                    source=reactor_name,
                    target=target,
                    intent=reaction_data.get("intent", "neutral"),
                    characters_dict=self.characters
                )

    def handle_voting_phase(self):
        print("\n--- PHASE: VOTING ---")
        # TODO: Implement voting logic
        self.state.phase = GamePhase.GAME_OVER # End loop for now
        
    def handle_night_phase(self):
        print("\n--- PHASE: NIGHT ---")
        # TODO: Implement werewolf targeting and ability usage
        pass

    def parse_player_intent(self, player_text: str) -> dict:
        """
        Takes raw player input and uses the LLM to map it to game mechanics,
        using the chat history to understand contextual replies.
        """
        if not player_text.strip():
            return {"intent": "neutral", "target": "None", "summary": "Remained silent"}

        # Pass the chat history to the prompt builder
        system_prompt = self.prompt_builder.build_intent_parser_prompt(
            alive_characters=self.state.alive_characters,
            chat_history=self.state.chat_history 
        )
        
        user_prompt = f"Player's Dialogue: \"{player_text}\""
        
        print("\n[System] Parsing Player Intent...")
        
        parsed_data = self.llm.generate_json(system_prompt, user_prompt)
        
        # Validation layer: Ensure the LLM didn't hallucinate a target
        target = parsed_data.get("target", "None")
        if target not in self.state.alive_characters and target != "None":
            print(f"[Warning] LLM hallucinated target '{target}'. Defaulting to 'None'.")
            parsed_data["target"] = "None"
            
        # Validation layer: Ensure intent is valid
        valid_intents = ["accuse", "defend", "agree", "disagree", "deflect", "question", "neutral"]
        if parsed_data.get("intent") not in valid_intents:
            parsed_data["intent"] = "neutral"
            
        return parsed_data
    
    def process_player_input(self, player_text: str):
        """
        Handles the full pipeline of a player's turn: 
        Parsing intent -> Updating Trust -> Appending to Chat History.
        """
        # 1. Parse the intent using the method we built earlier
        parsed_data = self.parse_player_intent(player_text)
        intent = parsed_data.get("intent", "neutral")
        target = parsed_data.get("target", "None")
        
        # 2. Apply the mathematical shift to the Trust Matrix
        TrustManager.apply_interaction(
            game_state=self.state,
            source="Player",
            target=target,
            intent=intent,
            characters_dict=self.characters
        )
        
        # 3. Add to the official chat log
        self.state.chat_history.append(f"[Player]: {player_text}")