from enum import Enum, auto

class GamePhase(Enum):
    PROLOGUE = auto()
    MORNING_REACTIONS = auto()
    DISCUSSION = auto()
    VOTING = auto()
    CONVERSATION = auto()
    NIGHT = auto()
    GAME_OVER = auto()

class GameState:
    def __init__(self, characters: list):
        self.phase = GamePhase.PROLOGUE
        self.day = 0
        self.chat_history = []
        self.public_events = []
        
        # Initialize Trust Matrix
        names = [c.name for c in characters] + ["Player"]
        self.trust_matrix = {
            name: {other: 50 for other in names if other != name} 
            for name in names
        }
        
        # Track who is alive
        self.alive_characters = [c.name for c in characters]