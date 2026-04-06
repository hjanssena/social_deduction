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
        """Concise personality. Kept short for small-model context budgets."""
        # Compact profile — one block, no redundant labels
        prompt = f"You are {character.name}, the {character.occupation}. {character.bio}\n"
        prompt += f"Personality: {character.archetype}\n\n"
        prompt += f"Stay in character as {character.name}. Speak in first person."
        return prompt

    @staticmethod
    def build_assertion_prompt(character_name: str, intent: str, target: str,
                               emotion: str, engine_reasoning: str,
                               chat_history: list[str], main_topic: str,
                               roster_text: str, character=None,
                               claims_text: str = "",
                               game_context: str = "") -> str:
        """Lean assertion prompt. Uses precise dictionary mapping for few-shot examples."""
        recent_history = chat_history[-4:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "(silence)"

        ACTION_DESCRIPTIONS = {
            "accuse": f"blame {{target}} — you believe {{target}} might be a werewolf",
            "defend_other": f"defend {{target}} — you believe {{target}} is innocent",
            "defend_self": f"deny accusations against {character_name}",
            "agree": f"support what {{target}} said",
            "disagree": f"argue against what {{target}} said",
            "question": f"demand {{target}} explain themselves",
            "deflect": f"change the subject away from {character_name}",
            "neutral": f"make a general observation about the werewolf situation",
        }
        action_desc = ACTION_DESCRIPTIONS.get(intent, "speak").format(target=target)

        prompt = "CONTEXT\n"
        prompt += f"Situation: {game_context}\n" if game_context else f"Situation: {main_topic}\n"
        prompt += f"Roster:\n{roster_text}\n"
        if claims_text:
            prompt += f"Role claims:\n{claims_text}\n"
        prompt += f"\nRecent assertions:\n{history_text}\n\n"

        prompt += "=== DIRECTIVE ===\n"
        prompt += f"Action: {action_desc}\n"
        prompt += f"Emotion: {emotion}\n"
        prompt += f"Reason: {engine_reasoning}\n"
        if character:
            prompt += f"Voice: {character.speech_pattern}\n\n"

        targeted_intents = {"accuse", "defend_other", "agree", "disagree", "question"}
        if intent in targeted_intents and target and target != "None":
            prompt += f"RULE: You MUST address {target} by their name in your dialogue. Do not use pronouns.\n\n"

        # --- EXACT DICTIONARY MATCH FEW-SHOT INJECTION ---
        if character and hasattr(character, "speech_examples") and isinstance(character.speech_examples, dict):
            intent_examples = character.speech_examples.get(intent, {})
            
            if isinstance(intent_examples, dict) and intent_examples:
                # 1. Reverse the string format to find the dictionary key
                template_key = engine_reasoning
                if target and target != "None":
                    template_key = engine_reasoning.replace(target, "{target}")
                
                # 2. Look up the exact example
                exact_example = intent_examples.get(template_key)
                
                # 3. Fallback: If exact match fails, grab the first available example for this intent
                if not exact_example:
                    exact_example = next(iter(intent_examples.values()), None)

                if exact_example:
                    prompt += "=== EXAMPLE OF HOW YOU SPEAK ===\n"
                    prompt += "Use this specific example to guide how you express your current reasoning:\n"
                    formatted_ex = exact_example.replace("{target}", target if target != "None" else "them")
                    prompt += f'- "{formatted_ex}"\n\n'

        prompt += 'Respond with ONLY a JSON object formatted exactly like this:\n'
        prompt += '{\n'
        prompt += '  "internal_monologue": "<1-2 sentences: Consider the context, your engine directive, and how your persona feels about this>",\n'
        prompt += '  "dialogue": "<Write 1-2 in-character sentences here>"\n'
        prompt += '}'

#        print(prompt)
        return prompt

    @staticmethod
    def build_reaction_prompt(character_name: str, intent: str, target: str,
                              emotion: str, engine_reasoning: str,
                              assertion_speaker: str, assertion_dialogue: str,
                              reaction_chain: list[dict], main_topic: str, roster_text: str,
                              character=None, claims_text: str = "",
                              game_context: str = "") -> str:
        """Ultra-minimal reaction prompt. Uses precise dictionary mapping for few-shot examples."""
        ACTION_VERBS = {
            "accuse": f"blame {target}",
            "defend_other": f"defend {target}",
            "defend_self": "deny the accusation",
            "agree": f"agree with {target}",
            "disagree": f"disagree with {target}",
            "question": f"question {target}",
            "deflect": "change the subject",
            "neutral": "make a general observation"
        }
        
        prompt = "CURRENT CONTEXT\n"
        prompt += f"Situation: {game_context}\n" if game_context else f"Situation: {main_topic}\n\n"
        prompt += f"Character roster: {roster_text}\n\n"
        action = ACTION_VERBS.get(intent, "react")

        prompt += f"THE TRIGGER (You are reacting to this):\n"
        prompt += f"{assertion_speaker} said: \"{assertion_dialogue}\"\n\n"

        if reaction_chain:
            prompt += "Other immediate reactions:\n"
            for r in reaction_chain[-2:]: 
                prompt += f"{r['speaker']} said: \"{r['dialogue']}\"\n"
            prompt += "\n"

        prompt += "YOUR TASK\n"
        prompt += f"You {action}. You feel {emotion}.\n"
        prompt += f"Reason: {engine_reasoning}\n"
        if character:
            prompt += f"Voice: {character.speech_pattern}\n\n"

        # --- EXACT DICTIONARY MATCH FEW-SHOT INJECTION ---
        if character and hasattr(character, "speech_examples") and isinstance(character.speech_examples, dict):
            intent_examples = character.speech_examples.get(intent, {})
            
            if isinstance(intent_examples, dict) and intent_examples:
                # 1. Reverse the string format to find the dictionary key
                template_key = engine_reasoning
                if target and target != "None":
                    template_key = engine_reasoning.replace(target, "{target}")
                
                # 2. Look up the exact example
                exact_example = intent_examples.get(template_key)
                
                # 3. Fallback: If exact match fails, grab the first available example for this intent
                if not exact_example:
                    exact_example = next(iter(intent_examples.values()), None)

                if exact_example:
                    prompt += "=== EXAMPLE OF HOW YOU SPEAK ===\n"
                    prompt += "Use this specific example to guide how you express your current reasoning:\n"
                    formatted_ex = exact_example.replace("{target}", target if target != "None" else "them")
                    prompt += f'- "{formatted_ex}"\n\n'

        prompt += 'Respond with ONLY a JSON object formatted exactly like this:\n'
        prompt += '{\n'
        prompt += '  "internal_monologue": "<1-2 sentences: Consider the context, your engine directive, and how your persona feels about this>",\n'
        prompt += '  "dialogue": "<Write 1 in-character short sentence here>"\n'
        prompt += '}'

        #print(prompt)
        return prompt

    @staticmethod
    def _extract_names(roster_text: str) -> list[str]:
        """Extract character names from roster lines like '- Elias: Blacksmith.'"""
        names = []
        for line in roster_text.split("\n"):
            line = line.strip().lstrip("- ")
            if ":" in line:
                names.append(line.split(":")[0].strip())
        return names

    @staticmethod
    def _build_parser_base(player_text: str, roster_text: str, context_text: str) -> str:
        """Shared parser structure for both assertion and reaction parsing."""
        names = PromptService._extract_names(roster_text)
        valid_targets = ", ".join(names) + ", None" if names else "None"

        prompt = "You are a game logic parser. Extract the player's intent as JSON.\n\n"

        prompt += """Intent definitions (target = the person your words are ABOUT):
- accuse: Blaming someone. Target = the accused.
- defend_other: Shielding someone. Target = person protected.
- defend_self: Denying accusations against yourself. Target = None.
- agree: Supporting someone's point. Target = person you agree with.
- disagree: Arguing against someone. Target = person you disagree with.
- deflect: Dodging or changing subject. Target = None.
- question: Asking someone to explain. Target = person asked.
- neutral: General statement. Target = None.

"""
        prompt += f"Roster:\n{roster_text}\n\n"
        prompt += f"Context:\n{context_text}\n\n"
        prompt += f"Examples:\n{PARSER_EXAMPLES}\n\n"
        prompt += f'Player said: "{player_text}"\n\n'
        prompt += f"Valid Targets: {valid_targets}\n"
        prompt += f"Valid Emotions: {VALID_EMOTIONS}\n\n"

        prompt += 'Respond with ONLY: {"intent": "<intent>", "target": "<name or None>", "emotion": "<emotion>"}\n'
        return prompt

    @staticmethod
    def build_assertion_parser_prompt(player_text: str, roster_text: str,
                                       chat_history: list[str]) -> str:
        """Parser for player assertions. Context = recent chat history."""
        recent = chat_history[-3:] if chat_history else []
        context_text = "\n".join(recent) if recent else "(no prior conversation)"
        return PromptService._build_parser_base(player_text, roster_text, context_text)

    @staticmethod
    def build_reaction_parser_prompt(player_text: str, roster_text: str,
                                      assertion_speaker: str, assertion_dialogue: str,
                                      reaction_chain: list[dict]) -> str:
        """Parser for player reactions. Context = assertion + sibling reactions."""
        lines = [f"{assertion_speaker} said: \"{assertion_dialogue}\""]
        for r in (reaction_chain or [])[-3:]:
            lines.append(f"{r['speaker']} said: \"{r['dialogue']}\"")
        context_text = "\n".join(lines)
        return PromptService._build_parser_base(player_text, roster_text, context_text)

    @staticmethod
    def build_role_reveal_prompt(character_name: str, claimed_role: str, findings: list[str],
                                  chat_history: list[str], is_pressure: bool = False,
                                  character=None) -> str:
        """Generates in-character dialogue for a role reveal (real or fake)."""
        recent_history = chat_history[-4:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "(silence)"

        ROLE_LABELS = {"guardian_angel": "Guardian Angel", "coroner": "Coroner"}
        label = ROLE_LABELS.get(claimed_role, claimed_role)

        prompt = f"Recent conversation:\n{history_text}\n\n"

        if is_pressure:
            prompt += f"Someone else just claimed to be the {label}. You must counter their claim NOW.\n"
        else:
            prompt += f"You have decided to reveal your role to the town.\n"

        prompt += f"YOUR ROLE: You are the {label}.\n"

        if findings:
            prompt += "YOUR FINDINGS (share these with the town):\n"
            for f in findings:
                prompt += f"  - {f}\n"
            prompt += "\n"
        else:
            prompt += "You have no findings to report yet.\n\n"

        prompt += f"Announce that you are the {label}. Share any findings clearly.\n"
        prompt += "Write 2-4 sentences. Use character names, not pronouns.\n"

        if character:
            prompt += f"Voice: {character.speech_pattern}\n"

        prompt += '\nRespond with ONLY: {"dialogue": "<your 2-4 sentences>"}\n'
        return prompt

    @staticmethod
    def build_morning_report_prompt(character_name: str, claimed_role: str,
                                     new_findings: list[str], chat_history: list[str],
                                     character=None) -> str:
        """Generates a morning report from a revealed role holder."""
        recent_history = chat_history[-3:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "(silence)"

        ROLE_LABELS = {"guardian_angel": "Guardian Angel", "coroner": "Coroner"}
        label = ROLE_LABELS.get(claimed_role, claimed_role)

        prompt = f"Recent events:\n{history_text}\n\n"
        prompt += f"You are the revealed {label}. Report your findings from last night.\n\n"

        if new_findings:
            prompt += "NEW FINDINGS:\n"
            for f in new_findings:
                prompt += f"  - {f}\n"
            prompt += "\n"
        else:
            prompt += "Nothing new to report.\n\n"

        prompt += "Share findings clearly in 1-3 sentences. Use character names, not pronouns.\n"

        if character:
            prompt += f"Voice: {character.speech_pattern}\n"

        prompt += '\nRespond with ONLY: {"dialogue": "<your 1-3 sentence report>"}\n'
        return prompt

    @staticmethod
    def build_wolf_whisper_prompt(speaker_name: str, occupation: str, target: str,
                                   engine_reasoning: str, valid_targets: list[str],
                                   chat_history: list[str], character=None) -> str:
        """Night phase: a fellow werewolf whispers their kill preference to the player."""
        recent_history = chat_history[-4:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "(silence)"

        prompt = "NIGHT PHASE. Whisper to your fellow werewolf about who to kill tonight.\n\n"

        prompt += f"Recent conversation:\n{history_text}\n\n"
        prompt += f"Your preference: Kill {target}.\n"
        prompt += f"Your reasoning: {engine_reasoning}\n"
        prompt += f"Living villagers: {', '.join(valid_targets)}\n\n"

        prompt += f"Name {target} as your kill choice. Give a brief reason. Use character names, not pronouns.\n"

        if character:
            prompt += f"Voice: {character.speech_pattern}\n"

        prompt += '\nRespond with ONLY: {"dialogue": "<your 1-2 sentence whisper>"}\n'
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

        prompt += "Write 1-3 sentences of final spoken dialogue. Raw emotion, no holding back.\n"
        prompt += "Use character names, not pronouns.\n"

        if character:
            prompt += f"Voice: {character.speech_pattern} {character.verbal_quirks}\n"

        prompt += "\nSpeak your final words:"
        return prompt
