import re

TRAVELER = "Player (the traveler)"

WOLF_WORDS = r"(werewol(f|ves)|wolf|wolves|beast)"
ROLE_NAMES = r"(guardian angel|coroner)"
ROLE_LABELS = {"guardian_angel": "Guardian Angel", "coroner": "Coroner"}


class ConversationController:
    """Small conversations between the traveler and one villager: introductions, remarks about the
    traveler's silence, and private chats. Every reply is checked for leaked secrets."""

    def __init__(self, gm):
        self.gm = gm

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------

    def introduce(self, name: str, transcript: list[str]) -> str:
        return self._line(name, transcript,
                          f"The traveler has just walked into the tavern. Introduce yourself to them the way "
                          f"{name} would: who you are, what you do here, and what you make of a stranger in "
                          f"town. This is a first meeting, not an interrogation. 2-3 sentences.")

    def reply(self, name: str, transcript: list[str], private: bool) -> str:
        where = "in private, away from the others" if private else "in front of the others at the tavern"
        return self._line(name, transcript,
                          f"The traveler just spoke to you, {where}. Reply the way {name} would: share what you "
                          f"think, ask them something, or keep your guard up. 1-3 sentences.", private=private,
                          replying=True)

    def remark_on_silence(self, name: str, introduced: str, transcript: list[str]) -> str:
        who = "you" if name == introduced else introduced
        return self._line(name, transcript,
                          f"{introduced} just introduced themselves to the traveler, who said nothing at all in "
                          f"return. Comment on the traveler's silence toward {who}, the way {name} would. "
                          f"1 sentence.")

    def open_chat(self, name: str) -> str:
        return self._line(name, [],
                          f"The traveler has sought you out for a private word, away from the others. Open the "
                          f"conversation the way {name} would, given everything that has happened so far. "
                          f"1-2 sentences.", private=True)

    # ------------------------------------------------------------------
    # Generation with the leak check
    # ------------------------------------------------------------------

    def _line(self, name: str, transcript: list[str], instruction: str, private: bool = False,
              replying: bool = False) -> str:
        gm = self.gm
        system = gm.npc_controller._system_prompt(name)
        pack_talk = private and self._is_packmate(name, "Player")
        notes = [self._own_vote(name, replying)]
        if pack_talk:
            notes.append("The traveler is your fellow werewolf. Nobody can hear you: speak freely, but quietly.")
        prompt = gm.prompt_builder.build_conversation_prompt(
            gm.characters[name], gm.get_game_context(), gm.get_roster_text(viewer=name),
            transcript, instruction, roles_known=gm.state.roles_known and not pack_talk,
            notes="\n- ".join(n for n in notes if n),
            claims_text=gm.get_claims_text(), own_claim=ROLE_LABELS.get(gm.state.revealed_roles.get(name), ""),
        )
        listener = "Player" if private else None
        line = self._clean(name, gm.llm.generate_text(system, prompt))
        if line and self.leaks_secret(name, line, listener):
            line = self._clean(name, gm.llm.generate_text(
                system, prompt + f'\n\nYou almost said: "{line}". That gives away a secret. Say something else.'))
        if not line or self.leaks_secret(name, line, listener):
            line = self._deflection(name)
        return line

    def _own_vote(self, name: str, replying: bool = False) -> str:
        """Reminds the speaker how they voted today; the whole town saw it, so there is no denying it.
        Before the first vote, only a reply to the traveler (who may bring one up) gets a reminder."""
        state = self.gm.state
        ballots = state.votes_by_day.get(state.day)
        if not state.votes_by_day:
            return "The town has never held a vote: nobody has voted for anyone." if replying else ""
        if not ballots or name not in ballots:
            return ""
        mine = ballots[name]
        vote = "abstained" if mine in (None, "None") else f"voted to hang {'the traveler' if mine == 'Player' else mine}"
        against = [v for v, t in ballots.items() if t == name]
        line = f"At today's vote you {vote}, in front of everyone."
        if against:
            line += f" {', '.join('The traveler' if v == 'Player' else v for v in against)} voted to hang you."
        return line

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
        if name in state.revealed_roles:  # already claimed in public: repeating the claim gives nothing away
            allow_claims = True
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
