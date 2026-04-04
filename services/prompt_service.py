class PromptService:
    
    @staticmethod
    def build_system_prompt(character, secret_role: str = "villager", known_werewolves: list = None) -> str:
        """Constructs concise personality and secret role directives."""
        # 1. Punchier Intro
        prompt = f"""You are {character.name}, the {character.occupation}.
Bio: {character.bio}
Traits: {character.archetype}
Speech Style: {character.speech_pattern} {character.verbal_quirks}

"""
        if secret_role == "werewolf":
            prompt += "SECRET ALIGNMENT: YOU ARE THE WEREWOLF (THE KILLER).\n"
            
            if known_werewolves and len(known_werewolves) > 1:
                pack = [w for w in known_werewolves if w != character.name]
                prompt += f"- YOUR FELLOW WEREWOLVES ARE: {', '.join(pack)}. Do not attack them, and secretly protect them if they are accused.\n"
            else:
                prompt += "- You are the only werewolf. Trust no one.\n"
                
            prompt += "- You committed the murders. You are actively lying to everyone.\n"
            prompt += "- CRITICAL RULE: NEVER confess. NEVER hint that you are the killer.\n"
            prompt += "- Goal: Act innocent, act scared or angry, and aggressively frame other innocent people to protect yourself.\n\n"
        else:
            prompt += "SECRET ALIGNMENT: YOU ARE AN INNOCENT VILLAGER.\n"
            prompt += "- You have no idea who the killer is.\n"
            prompt += "- Goal: Find the truth, survive, and lynch the real killer.\n\n"

        # 2. Moved to the bottom for maximum recency bias
        prompt += f"CRITICAL: Stay strictly in character as {character.name}. Speak in the first person ('I', 'me', 'my'). Embody your Traits and Speech Style completely. Do not be polite unless your profile demands it."
        
        return prompt

    @staticmethod
    def build_logic_prompt(logical_history: list[str], alive_characters: list[str], public_events: list[str], main_topic: str, speaker_name: str, window_size: int, current_event: str = None, relationship_context: str = None, player_status: str = None, roster_text: str = None) -> str:
        """Phase 1: The Brain. Analyzes state and outputs JSON intent."""
        recent_history = logical_history[-window_size:] if window_size > 0 else logical_history
        history_text = "\n".join(recent_history) if recent_history else "No prior actions."
        events_text = " | ".join(public_events) if public_events else "None."
        
        prompt = f"Today's Focus: {main_topic}\n"
        prompt += f"Timeline of Past Events: {events_text}\n\n"
        
        if roster_text:
            prompt += f"Room Roster:\n{roster_text}\n\n"
        if relationship_context:
            prompt += f"Current Feelings: {relationship_context}\n\n"
            
        prompt += f"Recent Logical Actions:\n{history_text}\n\n"
        
        # --- FIX: Prevent Logic Loops ---
        prompt += "Rules:\n"
        prompt += "1. Make a strategic decision strictly based on your Current Feelings and the Recent Actions.\n"
        prompt += "2. LOGICAL CONSISTENCY: Never defend someone you recently accused. Never accuse someone you recently defended. Hold your grudges.\n"
        prompt += "3. TACTICAL VARIETY: Do not repeat the exact same intent and target you used in your last action. If you just accused someone, change your reasoning, ask a question, or target someone else.\n"
        prompt += "4. Only use 'defend_other' on characters you ACTUALLY trust. If you distrust someone, keep attacking or suspecting them.\n"
        prompt += "5. If you want to calm the room down or make a general statement, use the 'neutral' intent with target 'None'.\n"
        prompt += f"6. You are {speaker_name}. Stay true to your traits.\n"

        if player_status == "dominating":
            prompt += "6. ALERT: Player is dominating. Consider confronting them.\n"
        elif player_status == "silent":
            prompt += "6. ALERT: Player is suspiciously silent. Consider questioning them.\n"
        
        if current_event:
            prompt += f"\nTask: React mechanically to this event -> {current_event}\n"
        else:
            prompt += "\nTask: It is your turn. Choose your next mechanical action.\n"
            
        valid_targets = [c for c in alive_characters if c != speaker_name]
            
        prompt += f"\nRespond ONLY in valid JSON. Valid Targets: {', '.join(valid_targets)} or 'None'.\n"
        prompt += """{
  "thought_process": "<Brief 1-sentence internal mechanical reasoning.>",
  "intent": "<Choose ONE: accuse|defend_other|defend_self|agree|disagree|deflect|question|neutral>",
  "target": "<Exact name from Valid Targets.>",
  "emotion": "<Choose EXACTLY ONE from Valid Emotions.>",
  "reasoning": "<Short 5-8 word summary of WHY you are taking this action.>"
}"""
        return prompt

    @staticmethod
    def build_narrative_prompt(speaker_name: str, intent: str, target: str, emotion: str, reasoning: str, chat_history: list[str], main_topic: str, public_events: list[str], roster_text: str, character=None) -> str:
        """Phase 2: The Mouth. Takes the logic and turns it into pure character dialogue."""
        recent_history = chat_history[-10:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "No prior conversation."
        
        events_text = " | ".join(public_events) if public_events else "None."

        prompt = f"You are {speaker_name}. You are currently feeling {emotion.upper()}.\n\n"
        
        prompt += f"Room Roster:\n{roster_text}\n\n"
        prompt += f"Current Topic: {main_topic}\n"
        prompt += f"Known Events: {events_text}\n\n"
        
        prompt += f"Recent Conversation:\n{history_text}\n\n"
        
        prompt += f"YOUR SCRIPT DIRECTION:\n"
        prompt += f"You must [{intent.upper()}] the target [{target.upper()}] because [{reasoning}].\n\n"
        
        prompt += "RULES FOR SPEAKING:\n"
        prompt += "1. Write EXACTLY one line of spoken, in-character dialogue. NO MORE.\n"
        prompt += "2. DO NOT output JSON. DO NOT summarize the script direction. Just act out the line.\n"
        prompt += "3. NO PROSE OR SCENE SETTING. DO NOT describe your actions (e.g., no 'I take a sip of ale', no asterisks).\n"
        prompt += "4. DO NOT prefix the line with your name.\n"
        prompt += "5. ANTI-MIRRORING: Never copy the phrasing, vocabulary, or sentence structure of the previous speaker. Maintain your unique voice.\n"
        prompt += "6. NO REPETITION: Do not repeat dialogue you have already said in the recent conversation.\n"
        prompt += "7. NO TITLE DROPPING: Do not mechanically announce your job or title (e.g., do not say 'As the blacksmith...'). Speak naturally.\n"
        
        if character:
            prompt += f"8. CRITICAL: You are {speaker_name}. {character.speech_pattern} {character.verbal_quirks}\n\n"
        else:
            prompt += f"8. CRITICAL: Express your assigned emotion heavily through your words.\n\n"
            
        # --- FIX: The Hard Stop Cue ---
        prompt += "Speak your line now:"
        
        return prompt

    @staticmethod
    def build_intent_parser_prompt(player_text: str, alive_characters: list[str], chat_history: list[str], roster_text: str = None) -> str:
        """Translates the player's text into the Logic Track with strict semantic definitions."""
        recent_history = chat_history[-3:] 
        history_text = "\n".join(recent_history) if recent_history else "No prior conversation."

        prompt = "You are a strict game logic parser for a social deduction game.\n"
        prompt += f"Character Roster:\n{roster_text}\n\n" if roster_text else ""
        prompt += f"Recent Chat History:\n{history_text}\n\n"
        prompt += f"Player's Spoken Text: \"{player_text}\"\n\n"

        valid_emotions = ["neutral", "happy", "angry", "suspicious", "fearful", "arrogant", "sad"]

        prompt += f"Valid Targets: {', '.join(alive_characters)} or 'None'.\n\n"
        
        prompt += """Valid Intents and Definitions:
- "defend_other": Protecting, supporting, or asking others to stop attacking a specific character (e.g., "Leave the mayor alone", "He needs time to explain").
- "accuse": Actively blaming someone for the crime or calling them suspicious.
- "defend_self": Justifying your own actions or denying an accusation against yourself.
- "agree": Siding with someone's previous point.
- "disagree": Arguing against someone's point without outright accusing them of the crime.
- "deflect": Dodging a question or trying to change the subject.
- "question": Asking someone directly for information.
- "neutral": General statements, calming the room, or making observations.

Targeting Rules:
1. Identify the PRIMARY beneficiary or victim of the player's action.
2. If the player says "Stop attacking Victor", the intent is "defend_other" and the target is "Victor".
3. Map titles/occupations (like "the mayor", "the baker") to their exact proper names using the Roster.\n\n"""

        prompt += f'Valid Emotions: {", ".join(valid_emotions)}\n\n'

        prompt += """You must respond ONLY with a raw JSON object. Do not include markdown formatting, backticks, or explanations. Use this EXACT structure:
{
  "intent": "<Choose EXACTLY ONE Valid Intent>",
  "target": "<The exact proper name of the target, or 'None'>",
  "emotion": "<Choose EXACTLY ONE Valid Emotion>",
  "summary": "<A brief 3-to-5 word summary>"
}"""
        return prompt
    
    @staticmethod
    def build_voting_prompt(character_name: str, alive_characters: list[str], chat_history: list[str], public_events: list[str], secret_role: str, relationship_context: str = None, roster_text: str = None) -> str:
        recent_history = chat_history[-10:] if chat_history else []
        history_text = "\n".join(recent_history) if recent_history else "No prior conversation."
        
        events_text = " | ".join(public_events) if public_events else "None."
        
        prompt = "It is time to vote. The town is deciding who to lynch.\n\n"
        
        if secret_role == "werewolf":
            prompt += "SECRET ALIGNMENT: YOU ARE THE WEREWOLF (THE KILLER).\n"
            prompt += "Goal: Vote for an innocent villager who is highly suspected by others. Protect yourself at all costs.\n\n"
        else:
            prompt += "SECRET ALIGNMENT: YOU ARE AN INNOCENT VILLAGER.\n"
            prompt += "Goal: Vote for the person you genuinely believe is the killer based on the discussion.\n\n"

        prompt += f"Timeline of Past Events: {events_text}\n\n"
        
        if roster_text:
            prompt += f"Room Roster:\n{roster_text}\n\n"
        if relationship_context:
            prompt += f"Current Feelings: {relationship_context}\n\n"

        prompt += f"Recent Chat:\n{history_text}\n\n"
        
        # --- FIX: Strip the speaker's name out of the valid voting targets list ---
        valid_targets = [c for c in alive_characters if c != character_name]
        
        prompt += f"Valid Targets to Vote For: {', '.join(valid_targets)} or 'None' to abstain.\n\n"
        prompt += "CRITICAL RULE: You cannot vote for yourself.\n\n"
        
        prompt += """Respond ONLY in valid JSON.
{
  "thought_process": "<Write your internal reasoning for this vote here>",
  "target": "<Exact name of the character from Valid Targets>"
}"""
        return prompt
    
    @staticmethod
    def build_night_action_prompt(character_name: str, valid_targets: list[str], logical_history: list[str], relationship_context: str) -> str:
        """Prompts an NPC werewolf to strategically select a victim."""
        recent_history = logical_history[-15:] if logical_history else []
        history_text = "\n".join(recent_history) if recent_history else "No prior actions."
        
        prompt = "It is the Night Phase. You are a WEREWOLF.\n"
        prompt += "Your goal is to choose one villager to murder tonight. Choose someone who is dangerous to you, highly trusted by the town, or onto your trail.\n\n"
        prompt += f"Recent Logical Actions:\n{history_text}\n\n"
        
        if relationship_context:
            prompt += f"Current Feelings: {relationship_context}\n\n"
            
        prompt += f"Valid Targets to Kill: {', '.join(valid_targets)}\n\n"
        prompt += """Respond ONLY in valid JSON.
{
  "thought_process": "<Write a 1-sentence whisper to your pack explaining why this target must die. Speak in the first person.>",
  "target": "<Exact name of the character from Valid Targets>"
}"""
        return prompt