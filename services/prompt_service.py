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
    def build_weaver_prompt(speaker_name: str, occupation: str, intent: str, target: str,
                            engine_reasoning: str, chat_history: list[str], main_topic: str,
                            public_events: list[str], roster_text: str,
                            claims_text: str = "") -> str:
        """Context Weaver: bridges engine math into narrative motivation. No dialogue."""
        recent_history = chat_history[-6:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "(silence)"
        events_text = " | ".join(public_events[-3:]) if public_events else "None."

        prompt = f"Setting: {main_topic}\n"
        prompt += f"Events: {events_text}\n"
        if claims_text:
            prompt += f"Role claims:\n{claims_text}\n"
        prompt += f"Roster:\n{roster_text}\n\n"
        prompt += f"Recent conversation:\n{history_text}\n\n"

        prompt += "ENGINE DIRECTIVE:\n"
        prompt += f"  Speaker: {speaker_name} ({occupation})\n"
        prompt += f"  Action: {speaker_name} will {intent.replace('_', ' ')} {target}\n"
        prompt += f"  Reasoning: {engine_reasoning}\n\n"

        prompt += f"Your job: As a THIRD-PERSON ANALYST (not the character), explain WHY {speaker_name} is doing this action.\n"
        prompt += "Write about the character, not as the character. Use ONLY proper character names. No pronouns like 'you' or 'they'.\n"
        prompt += "Do NOT write dialogue. Do NOT roleplay.\n"
        prompt += "NEVER mention secret roles (werewolf, guardian angel, coroner, villager) in your analysis.\n"
        prompt += "NEVER use engine action names like NEUTRAL-ing, ACCUSE-ing, AGREE-ing etc. Use natural language.\n\n"

        prompt += f"""Respond with ONLY a JSON object:
{{
  "situation_analysis": "<1-2 sentences: What just happened in the conversation that connects to {speaker_name}'s action?>",
  "narrative_motivation": "<1-2 sentences: Why {speaker_name} specifically targets {target} right now, grounded in recent events and {speaker_name}'s personality>"
}}"""
        return prompt

    @staticmethod
    def build_reaction_weaver_prompt(reactor_name: str, reactor_occupation: str,
                                     intent: str, target: str, engine_reasoning: str, intensity: str,
                                     speaker_name: str, speaker_dialogue: str, speaker_intent: str,
                                     chat_history: list[str], main_topic: str,
                                     public_events: list[str], roster_text: str,
                                     prev_reaction: dict = None,
                                     claims_text: str = "") -> str:
        """Reaction Weaver: isolates the claim being reacted to, bridges engine into narrative.

        Args:
            prev_reaction: If set, dict with {speaker, dialogue, intent} of the most recent
                           reaction in the chain. The weaver should reference BOTH the original
                           assertion (primary) and this previous reaction (secondary).
        """
        recent_history = chat_history[-6:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "(silence)"
        events_text = " | ".join(public_events[-3:]) if public_events else "None."

        prompt = f"Setting: {main_topic}\n"
        prompt += f"Events: {events_text}\n"
        if claims_text:
            prompt += f"Role claims:\n{claims_text}\n"
        prompt += f"Roster:\n{roster_text}\n\n"
        prompt += f"Recent conversation:\n{history_text}\n\n"

        prompt += "THE MAIN ASSERTION (this is what started the discussion):\n"
        prompt += f"  [{speaker_name}]: {speaker_dialogue}\n\n"

        if prev_reaction:
            prev_name = prev_reaction["speaker"]
            prev_dialogue = prev_reaction["dialogue"]
            prompt += "THE MOST RECENT REACTION (what was just said):\n"
            prompt += f"  [{prev_name}]: {prev_dialogue}\n\n"

        prompt += "ENGINE DIRECTIVE:\n"
        prompt += f"  Reactor: {reactor_name} ({reactor_occupation})\n"
        prompt += f"  Action: {reactor_name} will {intent.replace('_', ' ')} {target}\n"
        prompt += f"  Reasoning: {engine_reasoning}\n"
        prompt += f"  Intensity: {intensity}\n\n"

        prompt += f"Your job: As a THIRD-PERSON ANALYST (not the character), explain WHY {reactor_name} reacts this way.\n"
        prompt += f"Focus primarily on {speaker_name}'s main assertion."
        if prev_reaction:
            prompt += f" Also consider {prev_reaction['speaker']}'s recent reaction as secondary context."
        prompt += "\n"
        prompt += "Write about the character, not as the character. Use ONLY proper character names. No pronouns.\n"
        prompt += "Do NOT write dialogue. Do NOT roleplay.\n"
        prompt += "NEVER mention secret roles (werewolf, guardian angel, coroner, villager) in your analysis.\n"
        prompt += "NEVER use engine action names like NEUTRAL-ing, ACCUSE-ing, AGREE-ing etc. Use natural language.\n\n"

        prompt += f"""Respond with ONLY a JSON object:
{{
  "core_claim": "<1 sentence: What exactly did {speaker_name} claim or assert?>",
  "situation_analysis": "<1 sentence: How does {reactor_name}'s personality shape this response?>",
  "narrative_motivation": "<1-2 sentences: Why {reactor_name} reacts to {speaker_name}'s claim this way, grounded in personality and recent events>"
}}"""
        return prompt

    @staticmethod
    def build_actor_prompt(character_name: str, emotion: str, narrative_motivation: str,
                           chat_history: list[str], roster_text: str, character=None,
                           intent: str = "neutral", target: str = "None",
                           claims_text: str = "", main_topic: str = "") -> str:
        """The Actor: pure roleplay for assertions. Transforms motivation into spoken dialogue.

        chat_history should contain only assertions (no reactions) for this day.
        """
        recent_history = chat_history[-4:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "(silence)"

        # --- CONTEXT BLOCK (top — can fade) ---
        prompt = ""
        if character:
            prompt += f"You are {character_name}, the {character.occupation}. {character.bio}\n"
            prompt += f"Personality: {character.archetype}\n"
            prompt += f"Speech style: {character.speech_pattern}\n"
            prompt += f"Style inspiration (do NOT copy word-for-word): {character.verbal_quirks}\n\n"

        if main_topic:
            prompt += f"Today's discussion topic: {main_topic}\n"
        prompt += f"Roster:\n{roster_text}\n"
        if claims_text:
            prompt += f"Role claims:\n{claims_text}\n"
        prompt += f"\nRecent assertions:\n{history_text}\n\n"

        # --- DIRECTIVE BLOCK (bottom — strongest recall) ---
        ACTION_DESCRIPTIONS = {
            "accuse": f"{character_name} accuses {{target}} — blames {{target}} directly",
            "defend_other": f"{character_name} defends {{target}} — tells the room to leave {{target}} alone",
            "defend_self": f"{character_name} defends {character_name} — denies accusations against {character_name}",
            "agree": f"{character_name} agrees with {{target}} — supports what {{target}} said",
            "disagree": f"{character_name} disagrees with {{target}} — argues against {{target}}'s point",
            "question": f"{character_name} questions {{target}} — demands {{target}} explain",
            "deflect": f"{character_name} deflects — changes the subject away from {character_name}",
            "neutral": f"{character_name} observes — makes a general comment about the situation",
        }
        action_desc = ACTION_DESCRIPTIONS.get(intent, f"{character_name} speaks").format(target=target)

        prompt += "=== YOUR DIRECTIVE (you MUST follow this exactly) ===\n"
        prompt += f"Action: {action_desc}\n"
        prompt += f"Emotion: {emotion}\n"
        prompt += f"Motivation: {narrative_motivation}\n\n"

        prompt += "Write 1-3 sentences of spoken dialogue. No actions, no prose, no narration.\n"
        prompt += "Your dialogue must relate to today's discussion topic.\n"

        targeted_intents = {"accuse", "defend_other", "agree", "disagree", "question"}
        if intent in targeted_intents and target and target != "None":
            prompt += f"You MUST name {target} in your dialogue. NEVER use pronouns — always use character names.\n"
        elif intent in ("neutral", "deflect"):
            prompt += "Do NOT accuse or blame anyone specific. NEVER use pronouns — always use character names.\n"
        else:
            prompt += "NEVER use pronouns — always use character names.\n"

        prompt += "Your dialogue MUST match the action above. Do NOT contradict it.\n"
        prompt += "Do NOT repeat or paraphrase what others already said.\n\n"

        prompt += 'Respond with ONLY a JSON object:\n'
        prompt += '{"dialogue": "<Your 1-3 sentences of spoken dialogue>"}\n'

        return prompt

    @staticmethod
    def build_reaction_actor_prompt(character_name: str, emotion: str,
                                     narrative_motivation: str, intent: str, target: str,
                                     assertion_speaker: str, assertion_dialogue: str,
                                     reaction_chain: list[dict], main_topic: str,
                                     character=None, claims_text: str = "") -> str:
        """Reaction actor: generates a 1-sentence response to an assertion.

        Only sees: the original assertion, sibling reactions so far, and the day's theme.
        No full chat_history — keeps reactions focused on the assertion at hand.
        """
        # Intent → concrete action description
        ACTION_DESCRIPTIONS = {
            "accuse": f"{character_name} accuses {{target}} — blames {{target}} directly",
            "defend_other": f"{character_name} defends {{target}} — tells the room to leave {{target}} alone",
            "defend_self": f"{character_name} defends {character_name} — denies accusations",
            "agree": f"{character_name} agrees with {{target}} — supports what {{target}} said",
            "disagree": f"{character_name} disagrees with {{target}} — argues against {{target}}'s point",
            "question": f"{character_name} questions {{target}} — demands {{target}} explain",
            "deflect": f"{character_name} deflects — changes the subject",
        }
        action_desc = ACTION_DESCRIPTIONS.get(intent, f"{character_name} reacts").format(target=target)

        # --- CONTEXT BLOCK (top) ---
        prompt = ""
        if character:
            prompt += f"You are {character_name}, the {character.occupation}. {character.bio}\n"
            prompt += f"Personality: {character.archetype}\n"
            prompt += f"Speech style: {character.speech_pattern}\n\n"

        prompt += f"Today's discussion topic: {main_topic}\n"
        if claims_text:
            prompt += f"Role claims:\n{claims_text}\n"
        prompt += "\n"

        # The assertion being reacted to
        prompt += f"THE ASSERTION (what started this):\n"
        prompt += f"  [{assertion_speaker}]: {assertion_dialogue}\n\n"

        # Sibling reactions so far
        if reaction_chain:
            prompt += "REACTIONS SO FAR:\n"
            for r in reaction_chain:
                prompt += f"  [{r['speaker']}]: {r['dialogue']}\n"
            prompt += "\n"

        # --- DIRECTIVE BLOCK (bottom — strongest recall) ---
        prompt += "=== YOUR DIRECTIVE (you MUST follow this exactly) ===\n"
        prompt += f"Action: {action_desc}\n"
        prompt += f"Emotion: {emotion}\n"
        prompt += f"Motivation: {narrative_motivation}\n\n"

        prompt += "Write EXACTLY 1 sentence of spoken dialogue responding to the assertion above.\n"

        targeted_intents = {"accuse", "defend_other", "agree", "disagree", "question"}
        if intent in targeted_intents and target and target != "None":
            prompt += f"You MUST name {target} in your dialogue. NEVER use pronouns — always use character names.\n"
        else:
            prompt += "NEVER use pronouns — always use character names.\n"

        prompt += "Your dialogue MUST match the action above. Do NOT contradict it.\n"
        prompt += "Do NOT repeat or paraphrase what others already said.\n\n"

        prompt += 'Respond with ONLY a JSON object:\n'
        prompt += '{"dialogue": "<Your 1 sentence of spoken dialogue>"}\n'

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

        prompt += "Rules:\n"
        prompt += f"1. Announce that you are the {label}. Be dramatic — this is a big moment.\n"
        prompt += "2. If you have findings, share them clearly so the town understands.\n"
        prompt += "3. Write 2-4 sentences of spoken dialogue. No actions, no prose.\n"
        prompt += "4. NEVER use pronouns (you/he/she/they) to refer to anyone — always use their name.\n"

        if character:
            prompt += f"5. Speak in this style: {character.speech_pattern}\n"

        prompt += '\nRespond with ONLY a JSON object:\n'
        prompt += '{"dialogue": "<Your 2-4 sentences revealing your role and findings>"}\n'
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
        prompt += f"You are the revealed {label}. The town knows your role.\n"
        prompt += "Report your findings from last night to the town.\n\n"

        if new_findings:
            prompt += "NEW FINDINGS TO REPORT:\n"
            for f in new_findings:
                prompt += f"  - {f}\n"
            prompt += "\n"
        else:
            prompt += "You have nothing new to report.\n\n"

        prompt += "Rules:\n"
        prompt += "1. Share your new findings clearly and directly.\n"
        prompt += "2. Write 1-3 sentences of spoken dialogue. Be concise.\n"
        prompt += "3. NEVER use pronouns (you/he/she/they) to refer to anyone — always use their name.\n"

        if character:
            prompt += f"4. Speak in this style: {character.speech_pattern}\n"

        prompt += '\nRespond with ONLY a JSON object:\n'
        prompt += '{"dialogue": "<Your 1-3 sentence morning report>"}\n'
        return prompt

    @staticmethod
    def build_wolf_whisper_prompt(speaker_name: str, occupation: str, target: str,
                                   engine_reasoning: str, valid_targets: list[str],
                                   chat_history: list[str], character=None) -> str:
        """Night phase: a fellow werewolf whispers their kill preference to the player."""
        recent_history = chat_history[-4:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "(silence)"

        prompt = "NIGHT PHASE. You are whispering to your fellow werewolf about who to kill tonight.\n"
        prompt += "Speak in a hushed, conspiratorial tone. Be brief — 1-2 sentences.\n\n"

        prompt += f"Recent conversation:\n{history_text}\n\n"
        prompt += f"Your preference: Kill {target}.\n"
        prompt += f"Your reasoning: {engine_reasoning}\n"
        prompt += f"Living villagers: {', '.join(valid_targets)}\n\n"

        prompt += "Rules:\n"
        prompt += f"1. You MUST name {target} as your preferred kill.\n"
        prompt += "2. Give a brief in-character reason why this target is dangerous to the pack.\n"
        prompt += "3. NEVER use pronouns (you/he/she/they) to refer to anyone — always use their name.\n"

        if character:
            prompt += f"4. Speak in this style: {character.speech_pattern}\n"

        prompt += '\nRespond with ONLY a JSON object:\n'
        prompt += '{"dialogue": "<Your 1-2 sentence whisper>"}\n'
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
        prompt += "3. NEVER use pronouns (you/he/she/they) to refer to anyone — always use their name.\n"

        if character:
            prompt += f"4. Voice: {character.speech_pattern} {character.verbal_quirks}\n"

        prompt += "\nSpeak your final words:"
        return prompt

