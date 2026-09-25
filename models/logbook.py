"""Per-character private logbook: allegiances plus in-character diary entries.

The allegiance table (friends / enemies) is structured so the engine can route
events to the characters they concern; the entries are free text written by the
LLM in the character's own voice and are fed back into that character's prompts.
"""
import random


class Logbook:
    def __init__(self, owner: str, friends: list[str], enemies: list[str]):
        self.owner = owner
        self.friends = list(friends)
        self.enemies = list(enemies)
        self.pack = []  # Secret: fellow werewolves, pinned as allies at night 0 (see assign_pack)
        self.entries = []  # [{"day": int, "phase": str, "text": str}]

    def relation_to(self, name: str) -> str | None:
        """Returns 'friend', 'enemy' or None for how the owner sees `name`."""
        if name in self.friends:
            return "friend"
        if name in self.enemies:
            return "enemy"
        return None

    def assign_pack(self, pack: list[str]):
        """Pins the owner's fellow werewolves as allies: they can never be enemies again."""
        self.pack = [n for n in pack if n != self.owner]
        self.enemies = [n for n in self.enemies if n not in self.pack]

    def add_entry(self, day: int, phase: str, text: str):
        text = (text or "").strip()
        if text:
            self.entries.append({"day": day, "phase": phase, "text": text})

    def set_allegiances(self, friends: list[str], enemies: list[str], valid_names: list[str]):
        """Replaces the allegiance table with LLM-proposed lists, dropping unknown names.
        Pinned packmates are never touched."""
        valid = set(valid_names) - {self.owner} - set(self.pack)
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
            lines.append(f"Allies, your werewolf pack (secret, never say this aloud): {label(self.pack)}")

        entries = self.entries[-max_entries:] if max_entries else self.entries
        if entries:
            lines.append("Entries:")
            for e in entries:
                lines.append(f"[Day {e['day']}, {e['phase']}] {e['text']}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        return f"# {self.owner}'s logbook\n\n" + self.render().replace("\n", "\n\n")


def seed_logbooks(npc_names: list[str], config: dict) -> dict[str, Logbook]:
    """Gives every NPC a random set of friends and enemies among the other NPCs.
    Relationships tend to go both ways (mutual_friend_chance / mutual_enemy_chance).
    Roles play no part: packs are pinned later, at night 0. The Player starts as a stranger."""
    lo_f, hi_f = config.get("friends_count", [1, 2])
    lo_e, hi_e = config.get("enemies_count", [1, 1])
    mutual_friend = config.get("mutual_friend_chance", 0.7)
    mutual_enemy = config.get("mutual_enemy_chance", 0.5)

    want_friends = {n: random.randint(lo_f, hi_f) for n in npc_names}
    want_enemies = {n: random.randint(lo_e, hi_e) for n in npc_names}
    friends = {n: [] for n in npc_names}
    enemies = {n: [] for n in npc_names}

    def known(a, b):
        return b in friends[a] or b in enemies[a]

    order = list(npc_names)
    random.shuffle(order)
    for name in order:
        for table, want, mutual in ((friends, want_friends, mutual_friend), (enemies, want_enemies, mutual_enemy)):
            candidates = [n for n in npc_names if n != name and not known(name, n)]
            random.shuffle(candidates)
            while len(table[name]) < want[name] and candidates:
                other = candidates.pop()
                table[name].append(other)
                # Likely returned, if the other still has room and doesn't feel otherwise about them
                if random.random() < mutual and len(table[other]) < want[other] and not known(other, name):
                    table[other].append(name)

    return {n: Logbook(n, friends[n], enemies[n]) for n in npc_names}
