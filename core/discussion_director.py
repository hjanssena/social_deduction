import random
import re

from models.thread import Thread

PLAYER = "Player"


class DiscussionDirector:
    """Decides who holds the floor in the day's discussion; no LLM involved.

    The whole day is one thread about the killing. Whoever was asked or accused answers first; then
    people with a stake in the last lines may respond or pass. When the exchange runs dry (two passes
    in a row, or nobody with a stake), a "lead" turn moves the discussion on to another angle of the
    killing. The day ends when its line budget runs out."""

    def __init__(self, gm, rng=random):
        self.gm = gm
        self.rng = rng
        cfg = gm.config  # the "discussion" section of config.json
        self.turns_per_day = cfg.get("turns_per_day", 24)
        self.speaker_window = cfg.get("speaker_window", 6)
        self.max_in_window = cfg.get("max_in_window", 2)
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

    def day_over(self, thread: Thread) -> bool:
        """True once the line budget is spent. A question or accusation on the last line still gets its
        answer: one turn of overtime per day."""
        if self.budget_left():
            return False
        if not thread.overtime and self._answer_pending(thread):
            thread.overtime = True
            return False
        return True

    # --- who speaks -----------------------------------------------------------

    def next_speaker(self, thread: Thread) -> tuple[str | None, str]:
        """(name, role). role is "answer" for whoever owes an answer, "join" for someone responding to
        the last lines, "lead" when the exchange has run dry and someone should move it on (or open it)."""
        last = thread.last
        if last is None:
            return self.pick_lead(), "lead"
        if self._answer_pending(thread):
            return thread.owed, "answer"
        if thread.passes_in_a_row >= 2:
            return self.pick_lead(exclude=(last.speaker,)), "lead"

        candidates = [n for n in self._npcs()
                      if n != last.speaker and n not in thread.passed and self._room_to_speak(n, thread)]
        stakes = {n: self.stake(n, thread) for n in candidates}
        concerned = [n for n in candidates if stakes[n] > 0]
        if concerned:
            weights = [stakes[n] * self.gm.characters[n].assertion_drive for n in concerned]
            return self.rng.choices(concerned, weights=weights, k=1)[0], "join"
        if candidates and self.rng.random() < self.bystander_chance:
            return self.rng.choice(candidates), "join"
        return self.pick_lead(exclude=(last.speaker,)), "lead"

    def pick_lead(self, exclude: tuple = ()) -> str | None:
        """Who opens the discussion or moves it on: weighted by assertion drive, less likely right after
        leading, twice as likely for someone accused today who hasn't spoken since."""
        npcs = [n for n in self._npcs() if n not in exclude] or self._npcs()
        if not npcs:
            return None
        weights = [self.gm.characters[n].assertion_drive * self.multipliers.get(n, 1.0)
                   * (2 if self._accused_and_silent(n) else 1) for n in npcs]
        return self.rng.choices(npcs, weights=weights, k=1)[0]

    def led(self, name: str):
        self.multipliers[name] = self.multipliers.get(name, 1.0) * self.decay

    def stake(self, name: str, thread: Thread) -> int:
        """How much the last two lines concern `name`: 2 if they target or name them, their friend or
        packmate; 1 if they involve someone they have feelings about; 0 otherwise."""
        recent = thread.turns[-2:]
        if not recent:
            return 0
        if any(t.target == name or re.search(rf"\b{re.escape(name)}\b", t.dialogue, re.IGNORECASE)
               for t in recent):
            return 2
        book = self.gm.state.logbooks.get(name)
        if not book:
            return 0
        targets = [t.target for t in recent if t.target not in (None, "None")]
        if any(t in book.pack or book.relation_to(t) == "friend" for t in targets):
            return 2
        involved = [n for t in recent for n in (t.speaker, t.target) if n not in (None, "None", PLAYER, name)]
        return 1 if any(n in book.pack or book.relation_to(n) for n in involved) else 0

    # --- helpers ------------------------------------------------------------

    def _answer_pending(self, thread: Thread) -> bool:
        owed = thread.owed
        return bool(owed in self.gm.state.alive_characters and thread.last and owed != thread.last.speaker
                    and (owed != PLAYER or not thread.player_prompted))

    def _room_to_speak(self, name: str, thread: Thread) -> bool:
        """Nobody takes more than max_in_window of the last speaker_window lines (answers excepted)."""
        recent = thread.turns[-self.speaker_window:]
        return sum(1 for t in recent if t.speaker == name) < self.max_in_window

    def _npcs(self) -> list[str]:
        return [n for n in self.gm.state.alive_characters if n != PLAYER]

    def _accused_and_silent(self, name: str) -> bool:
        today = [r for r in self.gm.state.public_record if r["day"] == self.gm.state.day]
        last_accused = max((i for i, r in enumerate(today) if r["intent"] == "accuse" and r["target"] == name),
                           default=None)
        if last_accused is None:
            return False
        return not any(r["speaker"] == name for r in today[last_accused + 1:])
