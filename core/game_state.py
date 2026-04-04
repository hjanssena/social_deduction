import random
from enum import Enum
from core.trust_manager import TrustManager

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
        
        # Add the Player to the alive roster implicitly
        self.alive_characters = [c.name for c in characters] + ["Player"]
        
        # Everyone starts with neutral trust towards everyone else
        self.trust_matrix = {
            name: {other: TrustManager.TRUST_NEUTRAL for other in self.alive_characters if other != name}
            for name in self.alive_characters
        }
        
        # --- Secret Role Assignment ---
        self.roles = {name: "villager" for name in self.alive_characters}
        
        werewolf_count = config.get("setup", {}).get("werewolf_count", 1)
        npc_names = [c.name for c in characters]
        
        # Randomly pick the werewolves from the NPCs
        werewolves = random.sample(self.alive_characters, min(werewolf_count, len(self.alive_characters)))
        for w in werewolves:
            self.roles[w] = "werewolf"