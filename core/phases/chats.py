from core.game_state import GamePhase


class ChatsPhase:
    """Evening: private chats between the traveler and villagers (see conversation controller)."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        self.gm.state.phase = GamePhase.NIGHT
