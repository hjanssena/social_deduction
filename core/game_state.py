import random
from enum import Enum
from core.trust_manager import TrustManager

WIN_MESSAGES = {
    "village_wins": "\n\033[92m[VICTORY] All werewolves have been eliminated! The village is safe.\033[0m",
    "werewolves_win": "\n\033[91m[DEFEAT] The werewolves now outnumber the villagers. The town falls to the beasts.\033[0m",
}

class GamePhase(Enum):
    PROLOGUE = 0
    DISCUSSION = 1
    VOTING = 2
    NIGHT = 3
    GAME_OVER = 4

class GameState:
    def __init__(self, characters: list, config: dict):
        self.phase = GamePhase.PROLOGUE
        self.day = 0
        self.chat_history = []
        self.logical_history = []
        self.public_events = [] 
        self.player_actions_today = 0
        self.killed_last_night = []
        self.ga_protected_tonight = None
        self.ga_protected_last_night = None
        self.ga_protection_history = []  # ["Night 0: Protected Elias", ...]
        self.coroner_knowledge = []
        self.opinions = {}  # {viewer: {target: "short opinion"}} — computed at end of each day
        self.main_topic = "Victor's uncle has mysteriously disappeared. Someone in this room is responsible."
        
        # Add the Player to the alive roster implicitly
        self.alive_characters = [c.name for c in characters] + ["Player"]
        
        # Randomized starting trust — gives NPCs pre-existing opinions
        self.trust_matrix = {
            name: {other: random.randint(30, 70) for other in self.alive_characters if other != name}
            for name in self.alive_characters
        }
        
        # --- Secret Role Assignment ---
        self.roles = {}
        setup = config.get("setup", {})
        werewolf_count = setup.get("werewolf_count", 1)
        ga_count = setup.get("guardian_angel_count", 0)
        coroner_count = setup.get("coroner_count", 0)

        pool = list(self.alive_characters)
        random.shuffle(pool)

        assigned = 0
        for _ in range(min(werewolf_count, len(pool) - assigned)):
            self.roles[pool[assigned]] = "werewolf"
            assigned += 1
        for _ in range(min(ga_count, len(pool) - assigned)):
            self.roles[pool[assigned]] = "guardian_angel"
            assigned += 1
        for _ in range(min(coroner_count, len(pool) - assigned)):
            self.roles[pool[assigned]] = "coroner"
            assigned += 1
        for i in range(assigned, len(pool)):
            self.roles[pool[i]] = "villager"

    def check_win_condition(self) -> str | None:
        """Returns 'village_wins', 'werewolves_win', or None if the game continues."""
        alive_werewolves = [n for n in self.alive_characters if self.roles.get(n) == "werewolf"]
        alive_villagers = [n for n in self.alive_characters if self.roles.get(n) != "werewolf"]

        if len(alive_werewolves) == 0:
            return "village_wins"
        if len(alive_werewolves) >= len(alive_villagers):
            return "werewolves_win"
        return None

    def is_coroner_alive(self) -> bool:
        return any(self.roles.get(name) == "coroner" for name in self.alive_characters)