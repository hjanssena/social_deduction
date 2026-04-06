from core.controllers.npc_controller import NPCController
from core.controllers.player_controller import PlayerController
from core.game_state import GameState, GamePhase
from core.stat_engine import StatEngine
from core.io_handler import IOHandler
from core.phases import ProloguePhase, DiscussionPhase, VotingPhase, NightPhase


class GameMaster:
    def __init__(self, llm_service, prompt_service, characters, config, io=None):
        self.llm = llm_service
        self.prompt_builder = prompt_service
        self.config = config.get("discussion", {})
        self.debug = config.get("debug", {})
        self.io = io or IOHandler()
        self.characters = {c.name: c for c in characters}
        self.state = GameState(characters, config)

        # Sub-systems
        self.stat_engine = StatEngine(self.state, self.characters, config.get("engine", {}))
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
        self.io.show_system("Starting Game Loop...", style="info")

        while self.state.phase != GamePhase.GAME_OVER:
            handler = self.phases.get(self.state.phase)
            if handler:
                handler.run()
            else:
                self.io.show_system(f"Phase {self.state.phase} not implemented yet.", style="error")
                break

    # --- Shared helpers used by controllers and phases ---

    def get_roster_text(self, viewer: str = None) -> str:
        """Builds a brief summary of everyone currently alive, with opinions if available."""
        viewer_opinions = self.state.opinions.get(viewer, {}) if viewer else {}
        roster = []
        for name in self.state.alive_characters:
            if name == "Player":
                entry = "- Player: A traveler that arrived just to stay the night."
            else:
                char_obj = self.characters.get(name)
                if not char_obj:
                    continue
                entry = f"- {name}: {char_obj.occupation.capitalize()}."

            if viewer and name != viewer:
                opinion = viewer_opinions.get(name)
                if opinion:
                    entry += f" ({opinion})"
            roster.append(entry)
        return "\n".join(roster)

    def get_claims_text(self) -> str:
        """Builds a summary of all public role claims and their outcomes."""
        state = self.state
        if not state.revealed_roles:
            return ""

        ROLE_LABELS = {"guardian_angel": "Guardian Angel", "coroner": "Coroner"}
        lines = []
        for name, claimed_role in state.revealed_roles.items():
            label = ROLE_LABELS.get(claimed_role, claimed_role)
            alive = "alive" if name in state.alive_characters else "dead"

            # Check if coroner has verified this person
            verification = None
            for finding in state.coroner_knowledge:
                if name in finding:
                    if "werewolf" in finding:
                        verification = "confirmed werewolf by coroner"
                    elif "innocent" in finding:
                        verification = "confirmed innocent by coroner"

            entry = f"- {name} claimed {label} ({alive})"
            if verification:
                entry += f" [{verification}]"
            lines.append(entry)

        return "\n".join(lines)

    def condense_day_history(self):
        """At the start of a new day, condense the previous day's chat_history into a summary.
        Replaces old entries with the condensed version at the start of the list."""
        state = self.state
        if not state.chat_history:
            return

        # Build condensation prompt
        history_text = "\n".join(state.chat_history)
        system = "You are a concise game narrator. Summarize the key events and accusations."
        prompt = (
            f"Summarize Day {state.day - 1}'s discussion into 3-5 bullet points.\n"
            f"Focus on: who accused whom, who defended whom, any role reveals, and the overall mood.\n"
            f"Use exact character names. Be factual and brief.\n\n"
            f"Discussion:\n{history_text}\n\n"
            f"Respond with ONLY a JSON object:\n"
            f'{{"summary": "<3-5 bullet point summary>"}}'
        )

        result = self.llm.generate_json(system, prompt)
        summary = result.get("summary", "") if result else ""

        if summary:
            # Replace old history with condensed version
            state.chat_history = [f"[Summary of Day {state.day - 1}]: {summary}"]
        # If condensation fails, keep the raw history (better than losing it)

    def get_game_context(self) -> str:
        """Builds a situational summary explaining the werewolf game stakes for the current day."""
        state = self.state
        day = state.day

        if day == 0:
            return (
                f"This is a social deduction game set in a small village. "
                f"Werewolves have secretly infiltrated the group. "
                f"During the day, villagers discuss suspicions and vote to lynch one person. "
                f"At night, werewolves kill a villager. "
                f"Today is Day 0. {state.main_topic} "
                f"Tensions are rising as rumors of werewolves spread."
            )

        # Day 1+: reference what happened
        lines = [
            "This is a social deduction game. Werewolves hide among villagers. "
            "Each day the town votes to lynch a suspect. Each night the wolves kill someone."
        ]

        # Summarize deaths
        killed = state.killed_last_night
        if killed:
            lines.append(f"Last night, {', '.join(killed)} was killed by werewolves.")
        else:
            lines.append("Miraculously, no one died last night.")

        # Mention lynches from public_events
        lynch_events = [e for e in state.public_events if "lynched" in e.lower()]
        if lynch_events:
            lines.append(lynch_events[-1])

        lines.append(
            f"It is now Day {day}. {len(state.alive_characters)} people remain alive. "
            f"The town must find and eliminate the werewolves before they are outnumbered."
        )

        return " ".join(lines)

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
