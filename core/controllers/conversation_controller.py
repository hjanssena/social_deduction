import re

TRAVELER = "Player (the traveler)"

WOLF_WORDS = r"(werewol(f|ves)|wolf|wolves|beast)"
ROLE_NAMES = r"(guardian angel|coroner)"


class ConversationController:
    """Small conversations between the traveler and one villager: introductions, remarks about the
    traveler's silence, and private chats. Every reply is checked for leaked secrets."""

    def __init__(self, gm):
        self.gm = gm

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------

    def introduce(self, name: str, transcript: list[str]) -> str:
        return self._line(name, transcript, "introduction",
                          f"The traveler has just walked into the tavern. Introduce yourself the way {name} "
                          f"would: your name, and a quick reaction to a stranger turning up now.")

    def reply(self, name: str, transcript: list[str], private: bool) -> str:
        where = "in private" if private else "in front of the others"
        return self._line(name, transcript, "reply",
                          f"The traveler just spoke to you, {where}. Answer what they actually said, the way "
                          f"{name} would: push back, ask something back, or give a little away.", private=private)

    def remark_on_silence(self, name: str, introduced: str, transcript: list[str]) -> str:
        who = "you" if name == introduced else introduced
        return self._line(name, transcript, "remark",
                          f"{introduced} just introduced themselves to the traveler, who said nothing back. "
                          f"React to the traveler's silence toward {who}, the way {name} would.")

    def open_chat(self, name: str) -> str:
        return self._line(name, [], "opening",
                          f"The traveler has sought you out for a private word, away from the others. Open the "
                          f"conversation the way {name} would, given what has happened so far.", private=True)

    # ------------------------------------------------------------------
    # Generation with the leak check
    # ------------------------------------------------------------------

    DEFAULT_MAX_WORDS = {"introduction": 30, "reply": 28, "remark": 16, "opening": 22}

    def _line(self, name: str, transcript: list[str], kind: str, instruction: str, private: bool = False) -> str:
        gm = self.gm
        system = gm.npc_controller._system_prompt(name)
        max_words = gm.config_all.get("conversation", {}).get("max_words", {}).get(
            kind, self.DEFAULT_MAX_WORDS[kind])
        pack_talk = private and self._is_packmate(name, "Player")
        prompt = gm.prompt_builder.build_conversation_prompt(
            gm.characters[name], gm.get_game_context(), gm.get_roster_text(viewer=name),
            transcript, instruction, roles_known=gm.state.roles_known and not pack_talk,
            max_words=max_words,
            notes=("The traveler is your fellow werewolf. Nobody can hear you: speak freely, but quietly."
                   if pack_talk else ""),
        )
        listener = "Player" if private else None
        line = self._clean(name, gm.llm.generate_text(system, prompt))
        if line and self.leaks_secret(name, line, listener):
            line = self._clean(name, gm.llm.generate_text(
                system, prompt + f'\n\nYou almost said: "{line}". That gives away a secret. Say something else.'))
        if not line or self.leaks_secret(name, line, listener):
            line = self._deflection(name)
        return self.trim(line, max_words)

    @staticmethod
    def trim(text: str, max_words: int) -> str:
        """Keeps whole sentences while they fit in `max_words`; a single overlong sentence is cut short."""
        sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
        kept, count = [], 0
        for sentence in sentences:
            words = len(sentence.split())
            if kept and count + words > max_words:
                break
            kept.append(sentence)
            count += words
        result = " ".join(kept)
        words = result.split()
        if len(words) > max_words:
            result = " ".join(words[:max_words]).rstrip(",;:—-") + "…"
        return result

    def _is_packmate(self, name: str, other: str) -> bool:
        book = self.gm.state.logbooks.get(name)
        return bool(self.gm.state.roles_known and book and other in book.pack)

    @staticmethod
    def _clean(name: str, text: str) -> str:
        """Strips quotes and a leading speaker label ("[Elias]:", "Elias ->  Player:") if the model added one."""
        text = (text or "").strip().strip('"').strip()
        text = re.sub(rf"^\[?{re.escape(name)}[^:\]]*\]?:\s*", "", text)
        return text.strip().strip('"').strip()

    def _deflection(self, name: str) -> str:
        examples = self.gm.characters[name].speech_examples.get("deflect", {})
        lines = [v for v in examples.values() if "{target}" not in v]
        return lines[0] if lines else "I'd rather keep my thoughts to myself for now."

    def leaks_secret(self, name: str, text: str, listener: str = None, allow_claims: bool = False) -> bool:
        """True if `text` gives away the speaker's secret: a wolf owning up or naming its pack,
        or anyone claiming a role (claims only happen in public, through the discussion loop).
        Wolves talking privately to a packmate have no secret to keep from them.
        allow_claims: role claims are fine here (final words); only a wolf owning up counts."""
        state = self.gm.state
        if not state.roles_known or (listener and self._is_packmate(name, listener)):
            return False
        t = text.lower()
        role = state.roles.get(name)
        if not allow_claims:
            if re.search(rf"\b(i am|i'm|we are|we're)\s+(a |an |the )?{ROLE_NAMES}\b", t):
                return True
            if role == "guardian_angel" and re.search(r"\bi (protected|watched over|shielded)\b", t):
                return True
        if role == "werewolf":
            if re.search(rf"\b(i am|i'm|we are|we're)\s+(a |the |one of the )?{WOLF_WORDS}", t):
                return True
            if re.search(r"\b(we|us)\s+(were)?wol(f|ves)\b", t):
                return True
            if re.search(r"\b(my|our) (pack|kind)\b", t):
                return True
            book = state.logbooks.get(name)
            for mate in (book.pack if book else []):
                if re.search(rf"\b{re.escape(mate.lower())}\b", t) and re.search(rf"\b{WOLF_WORDS}", t) \
                        and re.search(r"\b(we|us|our|together|pack)\b", t):
                    return True
        return False
