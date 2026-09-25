"""Crime scene facts. The engine decides what was found; the LLM only writes the scene around it.

Each clue is a trace (a clue tag, such as "soot") found at a scene. A true clue fits the killing
wolf and at least one innocent; a red herring fits only innocents. Who it fits is never shown to
the villagers, only the trace itself.
"""
import random
from dataclasses import dataclass, field


@dataclass
class Clue:
    day: int
    victim: str
    location: str
    tag: str
    kind: str  # "true" | "herring"
    fits: list[str] = field(default_factory=list)  # Everyone alive who could have left this trace


class ClueLedger:
    def __init__(self):
        self.clues: list[Clue] = []

    def add(self, clue: Clue):
        self.clues.append(clue)

    def on_day(self, day: int) -> list[Clue]:
        return [c for c in self.clues if c.day == day]

    def render_public(self) -> str:
        """What the village knows: where each body was found and the traces beside it. No verdicts."""
        by_scene = {}
        for c in self.clues:
            by_scene.setdefault((c.day, c.victim, c.location), []).append(c.tag)
        return " ".join(f"Day {day}: {victim} was found at {location}, with traces of {', '.join(tags)}."
                        for (day, victim, location), tags in by_scene.items())


def carriers(tag: str, characters: dict, alive: list[str], player_tags: list[str]) -> list[str]:
    """Everyone alive whose clue tags include `tag`."""
    out = [n for n in alive if n in characters and tag in characters[n].clue_tags]
    if "Player" in alive and tag in player_tags:
        out.append("Player")
    return out


def plan_scene(day: int, victim: str, killer: str | None, roles: dict, alive: list[str],
               characters: dict, config: dict) -> tuple[str, list[Clue]]:
    """Picks the location and the clues for a killing.
    - A true clue (with probability true_clue_chance): a trace of the killer that at least one
      innocent also carries, so it narrows the field without naming anyone.
    - A red herring (always, when one exists): a trace that only innocents carry."""
    player_tags = config.get("player_tags", [])
    location = random.choice(config.get("locations", ["the edge of the woods"]))
    wolves = {n for n, r in roles.items() if r == "werewolf"}
    clues = []

    killer_tags = player_tags if killer == "Player" else getattr(characters.get(killer), "clue_tags", [])
    if killer and random.random() < config.get("true_clue_chance", 0.5):
        vague = [t for t in killer_tags
                 if len(fits := carriers(t, characters, alive, player_tags)) >= 2
                 and any(f not in wolves for f in fits)]
        if vague:
            tag = random.choice(vague)
            clues.append(Clue(day, victim, location, tag, "true", carriers(tag, characters, alive, player_tags)))

    innocent_tags = {t for n in alive if n not in wolves
                     for t in (player_tags if n == "Player" else getattr(characters.get(n), "clue_tags", []))}
    herrings = [t for t in sorted(innocent_tags)
                if not set(carriers(t, characters, alive, player_tags)) & wolves
                and t not in [c.tag for c in clues]]
    if herrings:
        tag = random.choice(herrings)
        clues.append(Clue(day, victim, location, tag, "herring", carriers(tag, characters, alive, player_tags)))

    random.shuffle(clues)  # The scene never lists the true clue first
    return location, clues
