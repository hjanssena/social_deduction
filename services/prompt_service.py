from models.character import Character

class PromptService:

    @staticmethod
    def build_discussion_prompt(chat_history: list[str], alive_characters: list[str], public_events: list[str], current_event: str = None) -> str:
        
        events_text = "\n".join(public_events) if public_events else "No major events have occurred yet."
        recent_history = chat_history[-5:]
        history_text = "\n".join(recent_history) if recent_history else "The room is quiet. No one has spoken yet."
        
        # 1. NEW: Explicitly explain the chat format to the LLM so it parses speakers correctly
        prompt = "You are currently in a group discussion. The chat history is formatted as [Speaker Name]: Message.\n\n"
        
        prompt += f"Key Public Events:\n{events_text}\n\n"
        prompt += f"Recent Chat History:\n{history_text}\n\n"
        
        if current_event:
            prompt += f"Current Event: {current_event}\nTask: React directly to this specific event based on your personality.\n"
        else:
            # 2. NEW: Stop forcing "new" assertions. Let them flow with the current context.
            prompt += "Task: It is your turn to speak. Continue the conversation naturally based on the Recent Chat History. You can respond to someone, defend someone, make an accusation, or change the subject.\n"
            
        prompt += f"""Valid Targets: {', '.join(alive_characters)}
        
Provide a JSON object with the following keys:
- "intent": (string) Choose EXACTLY ONE: "accuse", "defend", "agree", "disagree", "deflect", "question", "neutral".
- "target": (string) The exact name of the character your dialogue is directed at, or "None" if speaking to the whole room.
- "dialogue": (string) Your spoken response out loud to the room. Keep it short and conversational. Ensure it logically aligns with who you are addressing.
"""
        return prompt
    
    @staticmethod
    def build_intent_parser_prompt(alive_characters: list[str], chat_history: list[str]) -> str:
        """Constructs a strict logic prompt to classify free-text input, aware of recent context."""
        
        # Grab the last 3 messages to establish what the player is reacting to
        recent_history = chat_history[-3:] 
        history_text = "\n".join(recent_history) if recent_history else "No prior conversation."

        return f"""You are a strict game logic parser for a social deduction game.
Your task is to analyze the Player's dialogue in the context of the recent conversation and determine their intent and the target character.

Recent Chat History:
{history_text}

Valid Targets: {', '.join(alive_characters)}
Valid Intents: "accuse", "defend", "agree", "disagree", "deflect", "question", "neutral"

You must respond ONLY in valid JSON format with the following keys:
- "intent": (string) Choose EXACTLY ONE from the Valid Intents list.
- "target": (string) The exact name of the character targeted, or "None" if the statement is general.
- "summary": (string) A brief, 3-to-5 word summary of the player's core point.
"""