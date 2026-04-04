from core.controllers.npc_controller import NPCController
from core.controllers.player_controller import PlayerController
from core.game_state import GameState, GamePhase
from core.io_handler import IOHandler
from core.phases import ProloguePhase, DiscussionPhase, VotingPhase, NightPhase


class GameMaster:
    def __init__(self, llm_service, prompt_service, characters, config, io=None):
        self.llm = llm_service
        self.prompt_builder = prompt_service
        self.config = config
        self.io = io or IOHandler()
        self.characters = {c.name: c for c in characters}
        self.state = GameState(characters, config)

        # Sub-systems
        self.player_controller = PlayerController(self)
        self.npc_controller = NPCController(self)

        # Phase handlers
        self.phases = {
            GamePhase.PROLOGUE: ProloguePhase(self),
            GamePhase.DISCUSSION: DiscussionPhase(self),
            GamePhase.VOTING: VotingPhase(self),
            GamePhase.NIGHT: NightPhase(self),
        }

    def run_loop(self):
        """The main execution loop that routes to specific phase handlers."""
        self.io.display("Starting Game Loop...")

        while self.state.phase != GamePhase.GAME_OVER:
            handler = self.phases.get(self.state.phase)
            if handler:
                handler.run()
            else:
                self.io.display(f"Phase {self.state.phase} not implemented yet.")
                break

    # --- Shared helpers used by controllers and phases ---

    def get_roster_text(self) -> str:
        """Builds a brief summary of everyone currently alive in the room."""
        roster = ["- Player: A traveler that arrived just to stay the night."]
        for name in self.state.alive_characters:
            if name == "Player":
                continue
            char_obj = self.characters.get(name)
            if char_obj:
                roster.append(f"- {name}: {char_obj.occupation.capitalize()}.")
        return "\n".join(roster)

    def sanitize_target(self, target: str) -> str:
        """Ensures the target is a valid character name. Catches LLM occupation hallucinations."""
        if target in self.state.alive_characters or target == "None":
            return target

        target_lower = target.lower()
        for name in self.state.alive_characters:
            if name == "Player":
                continue
            char_obj = self.characters.get(name)
            if char_obj and char_obj.occupation.lower() in target_lower:
                return name

        return "None"
