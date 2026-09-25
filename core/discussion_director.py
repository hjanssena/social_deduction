import random
import re

from models.thread import Thread

PLAYER = "Player"


class DiscussionDirector:
    """Decides who holds the floor in the day's discussion; no LLM involved.

    One thread (topic) is open at a time. Within it, whoever was asked or accused answers first, then
    people with a stake in the exchange may join in, and the thread closes on its turn cap, on two passes
    in a row, when nobody is left to speak, or when the day's turn budget runs out."""

    def __init__(self, gm, rng=random):
        self.gm = gm
        self.rng = rng
        cfg = gm.config  # the "discussion" section of config.json
        self.turns_per_day = cfg.get("turns_per_day", 24)
        self.max_turns_per_thread = cfg.get("max_turns_per_thread", 6)
        self.max_turns_per_speaker = cfg.get("max_turns_per_speaker", 2)
        self.bystander_chance = cfg.get("bystander_chance", 0.3)
        self.decay = cfg.get("decay_factor", 0.5)
        self.turns_today = 0
        self.multipliers = {}

    # --- the day ------------------------------------------------------------

    def budget_left(self) -> bool:
        return self.turns_today < self.turns_per_day

    def count_turn(self):
        """A spoken line (passes are free)."""
        self.turns_today += 1

    def pick_opener(self, exclude: tuple = ()) -> str | None:
        """Who raises the next topic: weighted by assertion drive, less likely right after opening one,
        and twice as likely for someone accused today who hasn't spoken since."""
        npcs = [n for n in self._npcs() if n not in exclude]
        if not npcs:
            return None
        weights = [self.gm.characters[n].assertion_drive * self.multipliers.get(n, 1.0)
                   * (2 if self._accused_and_silent(n) else 1) for n in npcs]
        return self.rng.choices(npcs, weights=weights, k=1)[0]

    def opened(self, name: str):
        self.multipliers[name] = self.multipliers.get(name, 1.0) * self.decay

    # --- a thread -----------------------------------------------------------

    def close_reason(self, thread: Thread) -> str:
        """Why the thread should close now, or "" to go on. A question or accusation on the last allowed
        line still gets its answer: one turn of overtime per thread."""
        if thread.passes_in_a_row >= 2:
            return "passes"
        reason = ""
        if not self.budget_left():
            reason = "budget"
        elif len(thread.turns) >= self.max_turns_per_thread:
            reason = "turns"
        if reason and not thread.overtime and self._answer_pending(thread):
            thread.overtime = True
            return ""
        return reason

    def _answer_pending(self, thread: Thread) -> bool:
        owed = thread.owed
        return bool(owed in self.gm.state.alive_characters and thread.last and owed != thread.last.speaker
                     and (owed != PLAYER or not thread.player_prompted))

    def next_speaker(self, thread: Thread) -> tuple[str | None, str]:
        """(name, role): role is "answer" for whoever owes an answer, "join" otherwise.
        (None, "") when nobody is left, which closes the thread."""
        alive = self.gm.state.alive_characters
        last = thread.last
        owed = thread.owed
        if owed in alive and (last is None or owed != last.speaker):
            if owed != PLAYER or not thread.player_prompted:
                return owed, "answer"

        candidates = [n for n in self._npcs()
                      if (last is None or n != last.speaker) and n not in thread.passed
                      and thread.turns_by(n) < self.max_turns_per_speaker]
        if not candidates:
            return None, ""
        stakes = {n: self.stake(n, thread) for n in candidates}
        concerned = [n for n in candidates if stakes[n] > 0]
        if concerned:
            weights = [stakes[n] * self.gm.characters[n].assertion_drive for n in concerned]
            return self.rng.choices(concerned, weights=weights, k=1)[0], "join"
        if self.rng.random() < self.bystander_chance:
            return self.rng.choice(candidates), "join"
        return None, ""

    def stake(self, name: str, thread: Thread) -> int:
        """How much the last exchange concerns `name`: 2 if it targets or names them, their friend or
        packmate; 1 if it involves someone they have feelings about; 0 otherwise."""
        last = thread.last
        if last is None:
            return 0
        if last.target == name or re.search(rf"\b{re.escape(name)}\b", last.dialogue, re.IGNORECASE):
            return 2
        book = self.gm.state.logbooks.get(name)
        if not book:
            return 0
        target = last.target
        if target in book.pack or (target not in (None, "None") and book.relation_to(target) == "friend"):
            return 2
        involved = [n for n in (last.speaker, target, thread.opener) if n not in (None, "None", PLAYER, name)]
        return 1 if any(n in book.pack or book.relation_to(n) for n in involved) else 0

    # --- helpers ------------------------------------------------------------

    def _npcs(self) -> list[str]:
        return [n for n in self.gm.state.alive_characters if n != PLAYER]

    def _accused_and_silent(self, name: str) -> bool:
        today = [r for r in self.gm.state.public_record if r["day"] == self.gm.state.day]
        last_accused = max((i for i, r in enumerate(today) if r["intent"] == "accuse" and r["target"] == name),
                           default=None)
        if last_accused is None:
            return False
        return not any(r["speaker"] == name for r in today[last_accused + 1:])
