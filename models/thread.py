from dataclasses import dataclass, field

# Intents that leave the target owing an answer
ANSWER_OWED = ("question", "accuse")


@dataclass
class Turn:
    """One line spoken in a thread."""
    speaker: str
    intent: str
    target: str = "None"
    dialogue: str = ""

    def line(self) -> str:
        to = self.target if self.target not in (None, "", "None") else "Room"
        return f"[{self.speaker} -> {to}]: {self.dialogue}"


@dataclass
class Thread:
    """The day's discussion: one thread about the killing, from the first line to the last."""
    day: int
    opener: str
    topic: str = ""
    turns: list[Turn] = field(default_factory=list)
    owed: str | None = None  # who was asked or accused and hasn't spoken since
    passes_in_a_row: int = 0
    passed: set = field(default_factory=set)  # who passed since the last spoken line
    player_prompted: bool = False  # the Player gets one forced answer per thread
    overtime: bool = False  # one extra turn past the budget, so a last question still gets its answer
    ended: str = ""  # why it closed: "turns", "passes", "no one left", "budget"

    def add(self, turn: Turn):
        """Adds a spoken line and updates who owes an answer. Passes only hold for the exchange they were
        made in, so a spoken line clears them."""
        self.passes_in_a_row = 0
        self.passed = set()
        self.turns.append(turn)
        if turn.speaker == self.owed:
            self.owed = None
        if turn.intent in ANSWER_OWED and turn.target not in (None, "", "None", turn.speaker):
            self.owed = turn.target

    def add_pass(self, name: str = ""):
        self.passes_in_a_row += 1
        if name:
            self.passed.add(name)

    def close(self, reason: str):
        self.ended = reason

    @property
    def is_open(self) -> bool:
        return not self.ended

    def turns_by(self, name: str) -> int:
        return sum(1 for t in self.turns if t.speaker == name)

    @property
    def last(self) -> Turn | None:
        return self.turns[-1] if self.turns else None

    def participants(self) -> list[str]:
        return list(dict.fromkeys(t.speaker for t in self.turns))

    def render(self) -> str:
        """The whole exchange, in order, for prompts."""
        return "\n".join(t.line() for t in self.turns)

    def summary(self) -> str:
        """One line for EARLIER TODAY: the topic, who took part, and how it ended."""
        topic = self.topic or (self.turns[0].dialogue[:80] + "..." if self.turns else "something")
        if topic.split(" ", 1)[0] in ("The", "A", "An", "Who", "Why", "What", "Where", "How", "Whether"):
            topic = topic[0].lower() + topic[1:]
        others = [p for p in self.participants() if p != self.opener]
        line = f"{self.opener} raised {topic}"
        if others:
            line += f" ({', '.join(others)} joined in)"
        line += "."
        if self.owed:
            asker = next((t.speaker for t in reversed(self.turns) if t.target == self.owed), None)
            line += f" {self.owed} never answered{f' {asker}' if asker else ''}."
        return line
