import random
from enum import Enum
from core.trust_manager import TrustManager
from models.logbook import seed_logbooks

WIN_MESSAGES = {
    "village_wins": "All werewolves have been eliminated. The village is safe.",
    "werewolves_win": "The werewolves now equal the villagers. The town falls to the beasts.",
}

class GamePhase(Enum):
    ARRIVAL = 0
    NIGHT = 1
    MORNING = 2
    DISCUSSION = 3
    VOTING = 4
    AFTERMATH = 5
    CHATS = 6
    GAME_OVER = 7


PREMISE = ("A traveler arrives at a small, isolated village as night falls. "
           "Folk whisper that something has been hunting in the woods.")

class GameState:
    def __init__(self, characters: list, config: dict):
        self.phase = GamePhase.ARRIVAL
        self.day = 0
        self.chat_history = []
        self.logical_history = []
        self.public_events = [] 
        self.public_record = []  # [{day, speaker, intent, target, note, dialogue}] — every public action, see GameMaster.record_action
        self.player_actions_today = 0
        self.killed_last_night = []
        self.ga_protected_last_night = None
        self.ga_protection_history = []  # ["Night 1: Protected Elias", ...]
        self.attacked_last_night = None  # The wolves' target last night (known to the pack)
        self.saved_last_night = None  # Set when the Guardian Angel protected that target
        self.last_verdict = None  # {"day", "hanged": name or None, "text"} from the latest vote
        self.votes_by_day = {}  # {day: {voter: target or "None"}}
        self.coroner_knowledge = []
        self.opinions = {}  # {viewer: {target: "short opinion"}} — computed at end of each day
        self.contradiction_log = {}  # {name: [(day, intent, target), ...]}
        self.fake_claims = []  # [{claimant: str, claimed_role: str, day: int}]
        self.revealed_roles = {}  # {name: claimed_role} — public claims (real or fake)
        self.reveal_pressure = {}  # {name: claimed_role} — set when someone claims your role
        self.game_result = None  # Set by GameMaster.end_game
        self.roles_known = False  # Characters learn their own role at night 0
        self.morning_event = PREMISE  # What everyone woke up to: the premise, then each morning's news

        # Add the Player to the alive roster implicitly
        self.alive_characters = [c.name for c in characters] + ["Player"]

        self.suspicion_matrix = {
            name: {other: 0 for other in self.alive_characters if other != name}
            for name in self.alive_characters
        }
        
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

        # --- Private logbooks with randomized starting allegiances (roles play no part) ---
        npc_names = [c.name for c in characters]
        self.logbooks = seed_logbooks(npc_names, config.get("logbook", {}))

        # Transitional: keep the stat engine consistent with the logbook allegiances
        # until the LLM takes over decisions (stage 3 removes the trust matrix).
        for name, book in self.logbooks.items():
            for friend in book.friends:
                self.trust_matrix[name][friend] = random.randint(70, 85)
            for enemy in book.enemies:
                self.trust_matrix[name][enemy] = random.randint(15, 30)

    def check_win_condition(self) -> str | None:
        """Returns 'village_wins', 'werewolves_win', or None if the game continues."""
        alive_werewolves = [n for n in self.alive_characters if self.roles.get(n) == "werewolf"]
        alive_villagers = [n for n in self.alive_characters if self.roles.get(n) != "werewolf"]

        if len(alive_werewolves) == 0:
            return "village_wins"
        if len(alive_werewolves) >= len(alive_villagers):
            return "werewolves_win"
        return None

    def fake_claims_on(self, day: int) -> list[dict]:
        return [c for c in self.fake_claims if c.get("day") == day]

    def is_coroner_alive(self) -> bool:
        return any(self.roles.get(name) == "coroner" for name in self.alive_characters)