"""Per-character private logbook: allegiances plus in-character diary entries.

The allegiance table (friends / enemies) is structured so the engine can route
events to the characters they concern; the entries are free text written by the
LLM in the character's own voice and are fed back into that character's prompts.
"""
import random


class Logbook:
    def __init__(self, owner: str, friends: list[str], enemies: list[str], pack: list[str] = None):
        self.owner = owner
        self.friends = list(friends)
        self.enemies = list(enemies)
        self.pack = list(pack or [])  # Secret: fellow werewolves (werewolves only)
        self.entries = []  # [{"day": int, "phase": str, "text": str}]

    def relation_to(self, name: str) -> str | None:
        """Returns 'friend', 'enemy' or None for how the owner sees `name`."""
        if name in self.friends:
            return "friend"
        if name in self.enemies:
            return "enemy"
        return None

    def add_entry(self, day: int, phase: str, text: str):
        text = (text or "").strip()
        if text:
            self.entries.append({"day": day, "phase": phase, "text": text})

    def set_allegiances(self, friends: list[str], enemies: list[str], valid_names: list[str]):
        """Replaces the allegiance table with LLM-proposed lists, dropping unknown names."""
        valid = set(valid_names) - {self.owner}
        self.friends = [n for n in dict.fromkeys(friends) if n in valid]
        self.enemies = [n for n in dict.fromkeys(enemies) if n in valid and n not in self.friends]

    def render(self, alive: list[str] = None, max_entries: int = None) -> str:
        """Formats the logbook for inclusion in a prompt."""
        def label(names):
            if not names:
                return "(none)"
            return ", ".join(n if alive is None or n in alive else f"{n} (dead)" for n in names)

        lines = [f"Friends: {label(self.friends)}", f"Enemies: {label(self.enemies)}"]
        if self.pack:
            lines.append(f"SECRET - fellow werewolves (never say this aloud): {label(self.pack)}")

        entries = self.entries[-max_entries:] if max_entries else self.entries
        if entries:
            lines.append("Entries:")
            for e in entries:
                lines.append(f"[Day {e['day']}, {e['phase']}] {e['text']}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        return f"# {self.owner}'s logbook\n\n" + self.render().replace("\n", "\n\n")


def seed_logbooks(npc_names: list[str], roles: dict, config: dict) -> dict[str, Logbook]:
    """Gives every NPC a random set of friends and enemies among the other NPCs.
    The Player is a stranger to everyone and never appears in the starting table."""
    lo_f, hi_f = config.get("friends_count", [1, 2])
    lo_e, hi_e = config.get("enemies_count", [1, 1])
    wolves = [n for n, r in roles.items() if r == "werewolf"]  # May include the Player

    logbooks = {}
    for name in npc_names:
        others = [n for n in npc_names if n != name]
        random.shuffle(others)
        n_friends = min(random.randint(lo_f, hi_f), len(others))
        friends = others[:n_friends]
        pack = [w for w in wolves if w != name] if name in wolves else []
        # Werewolves never start out hating their own packmates
        remaining = [n for n in others[n_friends:] if n not in pack]
        enemies = remaining[:min(random.randint(lo_e, hi_e), len(remaining))]
        logbooks[name] = Logbook(name, friends, enemies, pack)
    return logbooks
