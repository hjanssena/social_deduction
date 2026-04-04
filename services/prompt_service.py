VALID_INTENTS = "accuse|defend_other|defend_self|agree|disagree|deflect|question|neutral"
VALID_EMOTIONS = "neutral|angry|suspicious|fearful|arrogant|sad|happy"

# One-shot example for the intent parser prompt
PARSER_EXAMPLE = """{
  "intent": "accuse",
  "target": "Elara",
  "emotion": "suspicious",
  "summary": "Blaming Elara for covering"
}"""


class PromptService:

    @staticmethod
    def build_system_prompt(character, secret_role: str = "villager", known_werewolves: list = None) -> str:
        """Concise personality + role directive. Kept short for small-model context budgets."""
        # Compact profile — one block, no redundant labels
        prompt = f"You are {character.name}, the {character.occupation}. {character.bio}\n"
        prompt += f"Personality: {character.archetype}\n\n"

        if secret_role == "werewolf":
            prompt += "SECRET: YOU ARE THE WEREWOLF (THE KILLER).\n"
            if known_werewolves and len(known_werewolves) > 1:
                pack = [w for w in known_werewolves if w != character.name]
                prompt += f"Your fellow werewolves: {', '.join(pack)}. Protect them secretly.\n"
            prompt += "NEVER confess. Frame others aggressively.\n\n"
        else:
            prompt += "SECRET: You are an INNOCENT VILLAGER. Find and lynch the killer.\n\n"

        prompt += f"Stay in character as {character.name}. Speak in first person."
        return prompt

    @staticmethod
    def build_logic_prompt(logical_history: list[str], alive_characters: list[str], public_events: list[str], main_topic: str, speaker_name: str, window_size: int, current_event: str = None, relationship_context: str = None, player_status: str = None, roster_text: str = None) -> str:
        """Phase 1: The Brain. Outputs a JSON intent decision. Kept compact for 7-11B models."""
        # Trim history windows aggressively — small models lose earlier entries anyway
        recent_history = logical_history[-min(window_size, 5):] if logical_history else []
        history_text = "\n".join(recent_history) if recent_history else "None."
        events_text = " | ".join(public_events[-3:]) if public_events else "None."

        prompt = f"Focus: {main_topic}\n"
        prompt += f"Events: {events_text}\n"

        if roster_text:
            prompt += f"Alive:\n{roster_text}\n"
        if relationship_context:
            prompt += f"Feelings: {relationship_context}\n"

        prompt += f"\nRecent Actions:\n{history_text}\n\n"

        # Rules — kept to 4 max so small models retain them
        prompt += "Rules:\n"
        prompt += "1. Base your decision on your Feelings and Recent Actions.\n"
        prompt += "2. Never defend someone you accused or accuse someone you defended.\n"
        prompt += "3. Do not repeat your last intent+target combo. Vary your actions.\n"
        prompt += f"4. You are {speaker_name}. Stay in character.\n"

        if player_status == "dominating":
            prompt += "ALERT: Player is dominating the conversation. Consider confronting them.\n"
        elif player_status == "silent":
            prompt += "ALERT: Player is suspiciously silent. Consider questioning them.\n"

        if current_event:
            prompt += f"\nReact to: {current_event}\n"
        else:
            prompt += "\nIt is your turn. Choose your action.\n"

        valid_targets = [c for c in alive_characters if c != speaker_name]

        prompt += f"\nValid Targets: {', '.join(valid_targets)}, None\n"
        prompt += f"Valid Intents: {VALID_INTENTS}\n"
        prompt += f"Valid Emotions: {VALID_EMOTIONS}\n\n"
        prompt += "Respond with ONLY a JSON object:\n"
        prompt += "{\n"
        prompt += '  "situation_analysis": "<1 sentence: What just happened and who is involved?>",\n'
        prompt += '  "strategic_thought": "<1 sentence: Given my role and feelings, what should I do?>",\n'
        prompt += f'  "intent": "<one of: {VALID_INTENTS}>",\n'
        prompt += '  "target": "<exact name from Valid Targets or None>",\n'
        prompt += f'  "emotion": "<one of: {VALID_EMOTIONS}>",\n'
        prompt += '  "reasoning": "<5-8 word summary of why>"\n'
        prompt += "}"
        return prompt

    @staticmethod
    def build_narrative_prompt(speaker_name: str, intent: str, target: str, emotion: str, reasoning: str, chat_history: list[str], main_topic: str, public_events: list[str], roster_text: str, character=None) -> str:
        """Phase 2: The Mouth. Converts logic output into one line of in-character dialogue."""
        recent_history = chat_history[-4:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "(silence)"
        events_text = " | ".join(public_events[-3:]) if public_events else "None."

        prompt = f"Setting: {main_topic}\n"
        prompt += f"Events: {events_text}\n"
        prompt += f"Roster: {roster_text}\n\n"
        prompt += f"Recent conversation:\n{history_text}\n\n"

        prompt += f"DIRECTION: You are {speaker_name}, feeling {emotion.upper()}. "
        prompt += f"[{intent.upper()}] targeting [{target.upper()}] because: {reasoning}.\n\n"

        prompt += "Rules:\n"
        prompt += "1. Write EXACTLY one line of spoken dialogue. No actions, no prose.\n"
        prompt += "2. Do not prefix with your name. Do not announce your job title.\n"

        if character:
            prompt += f"3. Voice: {character.speech_pattern} {character.verbal_quirks}\n"
        else:
            prompt += f"3. Express {emotion} strongly through your words.\n"

        # --- FIX: Switch entirely to a JSON schema ---
        prompt += "\nCRITICAL FORMATTING:\n"
        prompt += "You MUST respond with ONLY a valid JSON object. Use this exact format:\n"
        prompt += "{\n"
        prompt += '  "situation_analysis": "<1 sentence: What was just said and what is the immediate context?>",\n'
        prompt += '  "archetype_thought": "<1 sentence: How does your archetype influence your reaction?>",\n'
        prompt += '  "emotion_thought": "<1 sentence: What specific words/quirks will show your emotion?>",\n'
        prompt += '  "dialogue": "<Your EXACT one line of spoken dialogue>"\n'
        prompt += "}\n"

        return prompt

    @staticmethod
    def build_intent_parser_prompt(player_text: str, alive_characters: list[str], chat_history: list[str], roster_text: str = None) -> str:
        """Translates the player's raw text into a structured JSON intent."""
        recent_history = chat_history[-3:]
        history_text = "\n".join(recent_history) if recent_history else "No prior conversation."

        prompt = "You are a game logic parser. Extract the player's intent as JSON.\n\n"
        if roster_text:
            prompt += f"Roster:\n{roster_text}\n\n"
        prompt += f"Recent Chat:\n{history_text}\n\n"
        prompt += f'Player said: "{player_text}"\n\n'

        prompt += f"Valid Targets: {', '.join(alive_characters)}, None\n"
        prompt += f"Valid Intents: {VALID_INTENTS}\n"
        prompt += f"Valid Emotions: {VALID_EMOTIONS}\n\n"

        prompt += """Intent definitions:
- accuse: Blaming someone for the crime.
- defend_other: Protecting a specific character (target = the person being protected).
- defend_self: Denying an accusation against yourself.
- agree: Siding with someone's point.
- disagree: Arguing against someone's point.
- deflect: Dodging or changing the subject.
- question: Asking someone for information.
- neutral: General statements or observations.

Map titles ("the mayor", "the baker") to exact names from the Roster.

"""
        prompt += f"Example:\n{PARSER_EXAMPLE}\n\n"
        prompt += """Respond with ONLY a JSON object:
{
  "intent": "<one valid intent>",
  "target": "<exact name or None>",
  "emotion": "<one valid emotion>",
  "summary": "<3-5 word summary>"
}"""
        return prompt

    @staticmethod
    def build_voting_prompt(character_name: str, alive_characters: list[str], chat_history: list[str], public_events: list[str], secret_role: str, relationship_context: str = None, roster_text: str = None) -> str:
        recent_history = chat_history[-5:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "No conversation."
        events_text = " | ".join(public_events[-3:]) if public_events else "None."

        prompt = "VOTE: The town is deciding who to lynch.\n\n"

        if secret_role == "werewolf":
            prompt += "You are THE WEREWOLF. Vote for an innocent who others already suspect.\n\n"
        else:
            prompt += "You are INNOCENT. Vote for whoever you believe is the killer.\n\n"

        prompt += f"Events: {events_text}\n"
        if relationship_context:
            prompt += f"Feelings: {relationship_context}\n"
        prompt += f"\nRecent Chat:\n{history_text}\n\n"

        valid_targets = [c for c in alive_characters if c != character_name]
        prompt += f"Valid Targets: {', '.join(valid_targets)}, None (abstain)\n"
        prompt += "You cannot vote for yourself.\n\n"
        prompt += """Respond with ONLY a JSON object:
{
  "thought_process": "<1-sentence reasoning>",
  "target": "<exact name from Valid Targets>"
}"""
        return prompt

    @staticmethod
    def build_final_words_prompt(character_name: str, secret_role: str, alive_characters: list[str], chat_history: list[str], character=None) -> str:
        """Prompts a condemned character for their last words before execution."""
        recent_history = chat_history[-4:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "(silence)"

        prompt = f"You are {character_name}. The town has voted to execute you. You are being dragged to the gallows.\n"
        prompt += "This is your FINAL moment to speak.\n\n"

        if secret_role == "werewolf":
            prompt += "SECRET: You are the WEREWOLF. Use your last words to sow doubt and frame someone innocent.\n"
            prompt += "Make the town regret this. Point blame at a specific living person.\n\n"
        else:
            prompt += "SECRET: You are INNOCENT. You are about to die for a crime you did not commit.\n"
            prompt += "Use your last words to plead, accuse someone you suspect, or damn the town for their mistake.\n\n"

        others = [c for c in alive_characters if c != character_name]
        prompt += f"Still alive: {', '.join(others)}\n"
        prompt += f"Recent conversation:\n{history_text}\n\n"

        prompt += "Rules:\n"
        prompt += "1. Write 1-3 sentences of final spoken dialogue. Raw emotion, no holding back.\n"
        prompt += "2. No actions, no prose, no JSON. Just your spoken words.\n"

        if character:
            prompt += f"3. Voice: {character.speech_pattern} {character.verbal_quirks}\n"

        prompt += "\nSpeak your final words:"
        return prompt

    @staticmethod
    def build_night_action_prompt(character_name: str, valid_targets: list[str], logical_history: list[str], relationship_context: str) -> str:
        """Prompts an NPC werewolf to select a kill target."""
        recent_history = logical_history[-5:] if logical_history else []
        history_text = "\n".join(recent_history) if recent_history else "No prior actions."

        prompt = "NIGHT PHASE: You are a WEREWOLF. Choose one villager to murder.\n"
        prompt += "Pick someone dangerous to you, highly trusted, or onto your trail.\n\n"
        prompt += f"Recent Actions:\n{history_text}\n"

        if relationship_context:
            prompt += f"Feelings: {relationship_context}\n"

        prompt += f"\nValid Targets: {', '.join(valid_targets)}\n\n"
        prompt += """Respond with ONLY a JSON object:
{
  "thought_process": "<1-sentence reason to kill this target>",
  "target": "<exact name from Valid Targets>"
}"""
        return prompt
