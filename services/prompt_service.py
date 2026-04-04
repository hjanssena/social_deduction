VALID_INTENTS = "accuse|defend_other|defend_self|agree|disagree|deflect|question|neutral"
VALID_EMOTIONS = "neutral|angry|suspicious|fearful|arrogant|sad|happy"

# One-shot example for the intent parser prompt
PARSER_EXAMPLES = """Input: "I think Elara is hiding something, she was too quiet yesterday."
Output: {"analysis": "Blaming Elara for being suspicious", "intent": "accuse", "target": "Elara", "emotion": "suspicious", "summary": "Accusing Elara of hiding"}

Input: "Leave Garrick alone, he's done nothing wrong!"
Output: {"analysis": "Protecting Garrick from accusations", "intent": "defend_other", "target": "Garrick", "emotion": "angry", "summary": "Defending Garrick from blame"}

Input: "I wasn't even near the estate that night!"
Output: {"analysis": "Denying personal involvement", "intent": "defend_self", "target": "None", "emotion": "fearful", "summary": "Denying own involvement"}"""


class PromptService:

    @staticmethod
    def build_system_prompt(character, secret_role: str = "villager", known_werewolves: list = None, coroner_knowledge: list = None, ga_protection_history: list = None) -> str:
        """Concise personality + role directive. Kept short for small-model context budgets."""
        # Compact profile — one block, no redundant labels
        prompt = f"You are {character.name}, the {character.occupation}. {character.bio}\n"
        prompt += f"Personality: {character.archetype}\n\n"

        if secret_role == "werewolf":
            prompt += "SECRET: YOU ARE THE WEREWOLF (THE KILLER).\n"
            if known_werewolves and len(known_werewolves) > 1:
                pack = [w for w in known_werewolves if w != character.name]
                prompt += f"Your fellow werewolves: {', '.join(pack)}. Protect them secretly.\n"
            prompt += "NEVER confess. Frame others aggressively.\n"
            prompt += "DECEPTION TOOLS: You may falsely claim to be the Guardian Angel or Coroner to gain trust.\n"
            prompt += "Example: 'I protected someone last night' or 'As coroner, I saw they were innocent.'\n\n"
        elif secret_role == "guardian_angel":
            prompt += "SECRET: You are the GUARDIAN ANGEL. You protect one person each night.\n"
            prompt += "You may reveal this to gain trust, or stay hidden to avoid werewolf targeting.\n\n"
        elif secret_role == "coroner":
            prompt += "SECRET: You are the CORONER. After each lynch, you learn the victim's true role.\n"
            prompt += "You may share findings during discussion to guide the town.\n\n"
        else:
            prompt += "SECRET: You are an INNOCENT VILLAGER. Find and lynch the werewolves.\n\n"

        if secret_role == "guardian_angel" and ga_protection_history:
            prompt += "YOUR PROTECTION LOG:\n"
            for entry in ga_protection_history:
                prompt += f"- {entry}\n"
            prompt += "\n"

        if secret_role == "coroner" and coroner_knowledge:
            prompt += "YOUR FINDINGS:\n"
            for finding in coroner_knowledge:
                prompt += f"- {finding}\n"
            prompt += "\n"

        prompt += f"Stay in character as {character.name}. Speak in first person."
        return prompt

    @staticmethod
    def build_logic_prompt(logical_history: list[str], alive_characters: list[str], public_events: list[str], main_topic: str, speaker_name: str, window_size: int, current_event: str = None, relationship_context: str = None, player_status: str = None, roster_text: str = None, coroner_findings: str = None, secret_role: str = "villager", ga_log: str = None) -> str:
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
        if coroner_findings:
            prompt += f"Your coroner findings: {coroner_findings}\n"
        if ga_log:
            prompt += f"Your protection log: {ga_log}\n"

        prompt += f"\nRecent Actions:\n{history_text}\n\n"

        # Rules — kept to 4 max so small models retain them
        prompt += "Rules:\n"
        prompt += "1. Base your decision on your Feelings and Recent Actions.\n"
        prompt += "2. Never defend someone you accused or accuse someone you defended.\n"
        prompt += "3. Do not repeat your last intent+target combo. Vary your actions.\n"
        prompt += f"4. You are {speaker_name}. Stay in character.\n"

        if secret_role == "werewolf":
            prompt += "STRATEGY: You are the WEREWOLF. Deflect suspicion from yourself. Accuse innocents who are onto you. Defend your pack. Never reveal yourself.\n"
        elif secret_role == "guardian_angel":
            prompt += "STRATEGY: You are the GUARDIAN ANGEL. Help find the werewolf. Consider revealing your role only if it saves an innocent.\n"
        elif secret_role == "coroner":
            prompt += "STRATEGY: You are the CORONER. Use your findings to steer the town toward the truth.\n"

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
        if secret_role == "werewolf":
            prompt += '  "strategic_thought": "<1 sentence: How do I deflect suspicion and frame someone?>",\n'
        else:
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

        prompt += f"DIRECTIVE: You are {speaker_name}, feeling {emotion.upper()}. "
        prompt += f"Your goal is to [{intent.upper()}] targeting [{target.upper()}] because: {reasoning}.\n"
        prompt += "Your dialogue MUST clearly express this intent.\n\n"

        prompt += "Rules:\n"
        prompt += "1. Write EXACTLY one line of spoken dialogue. No actions, no prose.\n"
        prompt += "2. Do not prefix with your name. Do not announce your job title.\n"

        if character:
            prompt += f"3. Voice: {character.speech_pattern} {character.verbal_quirks}\n"
        else:
            prompt += f"3. Express {emotion} strongly through your words.\n"

        prompt += "\nYou MUST respond with ONLY a valid JSON object:\n"
        prompt += "{\n"
        prompt += '  "situation_analysis": "<1 sentence: What was just said?>",\n'
        prompt += f'  "intent_plan": "<1 sentence: How will I [{intent.upper()}] {target} in my own voice?>",\n'
        prompt += f'  "dialogue": "<Your one line of spoken dialogue that {intent.upper()}S {target}>"\n'
        prompt += "}\n"

        return prompt

    @staticmethod
    def build_intent_parser_prompt(player_text: str, alive_characters: list[str], chat_history: list[str], roster_text: str = None) -> str:
        """Translates the player's raw text into a structured JSON intent."""
        recent_history = chat_history[-3:]
        history_text = "\n".join(recent_history) if recent_history else "No prior conversation."

        prompt = "You are a game logic parser. Extract the player's intent as JSON.\n\n"

        prompt += """Intent definitions (target = the person your words are ABOUT):
- accuse: Blaming someone. Target = the accused person.
- defend_other: Shielding someone from blame. Target = person you are protecting.
- defend_self: Denying accusations against yourself. Target = None.
- agree: Supporting what someone said. Target = person you agree with.
- disagree: Arguing against someone's point. Target = person you disagree with.
- deflect: Dodging, changing subject, or being vague. Target = None.
- question: Asking someone for information. Target = person being asked.
- neutral: General statements with no clear target. Target = None.

"""
        if roster_text:
            prompt += f"Roster (map titles like 'the mayor' to exact names):\n{roster_text}\n\n"
        prompt += f"Recent Chat:\n{history_text}\n\n"

        prompt += f"Examples:\n{PARSER_EXAMPLES}\n\n"

        prompt += f'NOW PARSE THIS — Player said: "{player_text}"\n\n'
        prompt += f"Valid Targets: {', '.join(alive_characters)}, None\n"
        prompt += f"Valid Emotions: {VALID_EMOTIONS}\n\n"

        prompt += """Respond with ONLY a JSON object:
{
  "analysis": "<1 sentence: What is the player doing and to whom?>",
  "intent": "<one valid intent>",
  "target": "<exact name from Valid Targets or None>",
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
            prompt += "You are THE WEREWOLF. Vote for an innocent who others already suspect.\n"
            prompt += "You may claim to be the Guardian Angel or Coroner to justify your vote.\n\n"
        elif secret_role == "guardian_angel":
            prompt += "You are the GUARDIAN ANGEL. Vote for whoever you believe is the killer.\n"
            prompt += "Consider revealing your role if it helps save an innocent.\n\n"
        elif secret_role == "coroner":
            prompt += "You are the CORONER. Use your findings to guide your vote.\n\n"
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
        elif secret_role == "guardian_angel":
            prompt += "SECRET: You are the GUARDIAN ANGEL. Use your last words to reveal this if you wish.\n"
            prompt += "Plead for the town to protect themselves without you.\n\n"
        elif secret_role == "coroner":
            prompt += "SECRET: You are the CORONER. Use your last words to share any findings.\n"
            prompt += "The town loses your insight after this.\n\n"
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

    @staticmethod
    def build_ga_night_prompt(character_name: str, valid_targets: list[str], last_protected: str, logical_history: list[str], relationship_context: str) -> str:
        """Prompts an NPC Guardian Angel to select a protection target."""
        recent_history = logical_history[-5:] if logical_history else []
        history_text = "\n".join(recent_history) if recent_history else "No prior actions."

        prompt = "NIGHT PHASE: You are the GUARDIAN ANGEL. Choose one person to protect from the werewolf.\n"
        prompt += "Pick someone you think the werewolves will target tonight.\n\n"
        prompt += f"Recent Actions:\n{history_text}\n"

        if relationship_context:
            prompt += f"Feelings: {relationship_context}\n"

        if last_protected:
            prompt += f"\nYou CANNOT protect {last_protected} (protected last night).\n"

        prompt += f"\nValid Targets: {', '.join(valid_targets)}\n\n"
        prompt += """Respond with ONLY a JSON object:
{
  "thought_process": "<1-sentence reason to protect this target>",
  "target": "<exact name from Valid Targets>"
}"""
        return prompt
