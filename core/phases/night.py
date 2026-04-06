import random
from collections import Counter

from core.game_state import GamePhase, WIN_MESSAGES
from core.trust_manager import TrustManager


class NightPhase:
    """Handles win-condition checks, werewolf kill selection, and kill execution."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state

        # Compute opinions from the day's interactions before night resolves
        state.opinions = TrustManager.compute_opinions(state)

        io.show_phase("THE NIGHT PHASE", state.day)

        result = state.check_win_condition()
        if result:
            io.show_game_over(result, WIN_MESSAGES[result])
            state.phase = GamePhase.GAME_OVER
            return

        alive_werewolves = [name for name in state.alive_characters if state.roles.get(name) == "werewolf"]
        alive_villagers = [name for name in state.alive_characters if state.roles.get(name) != "werewolf"]

        # --- Guardian Angel Phase ---
        protected_target = self._resolve_ga_protection()
        state.ga_protected_tonight = protected_target

        if protected_target:
            state.ga_protection_history.append(f"Night {state.day}: Protected {protected_target}")

        # --- Werewolf Kill Phase ---
        killed_target = self._resolve_kill(alive_werewolves, alive_villagers)

        # --- Protection Check ---
        if killed_target and killed_target == protected_target:
            io.show_system("The morning sun rises. Miraculously, everyone survived the night.", style="success")
            state.public_events.append(f"Night {state.day}: No one was killed.")
            state.main_topic = "No one died last night, but the killer is still out there."
            state.killed_last_night = []
        else:
            self._execute_kill(killed_target)

        # Rotate GA protection memory
        state.ga_protected_last_night = state.ga_protected_tonight
        state.ga_protected_tonight = None

        if state.phase != GamePhase.GAME_OVER:
            io.pause()
            state.day += 1
            state.phase = GamePhase.DISCUSSION

    def _resolve_kill(self, alive_werewolves, alive_villagers) -> str:
        """Determines who the werewolves kill tonight."""
        gm = self.gm
        io = gm.io

        if "Player" in alive_werewolves:
            return self._player_werewolf_kill(alive_werewolves, alive_villagers)

        io.show_system("The village sleeps... but something evil stalks the night.", style="muted")

        votes = []
        for npc in alive_werewolves:
            pref = gm.npc_controller.generate_kill_preference(npc, alive_villagers)
            if pref["target"] in alive_villagers:
                votes.append(pref["target"])

        if votes:
            return Counter(votes).most_common(1)[0][0]
        return random.choice(alive_villagers)

    def _player_werewolf_kill(self, alive_werewolves, alive_villagers) -> str:
        """Handles kill selection when the player is a werewolf."""
        gm = self.gm
        io = gm.io

        npc_wolves = [w for w in alive_werewolves if w != "Player"]
        if npc_wolves:
            io.show_system("Your fellow werewolves whisper their desires in the dark...", style="muted")
            for npc in npc_wolves:
                whisper = gm.npc_controller.generate_wolf_whisper(npc, alive_villagers)
                io.show_dialogue(npc, "Pack", whisper["dialogue"], intent="whisper")
        else:
            io.show_system("You are the lone werewolf. The choice is yours entirely.", style="error")

        return gm.player_controller.get_kill_target(alive_villagers)

    def _execute_kill(self, killed_target):
        """Applies the kill to game state and checks for player death."""
        gm = self.gm
        io = gm.io
        state = gm.state

        state.killed_last_night = []

        if killed_target and killed_target != "None":
            io.show_death(killed_target, "killed")

            state.alive_characters.remove(killed_target)
            state.killed_last_night.append(killed_target)
            state.public_events.append(
                f"Night {state.day}: {killed_target} was brutally killed by the werewolves."
            )
            state.main_topic = f"{killed_target} was murdered last night. The killer is still among us."

            if killed_target == "Player":
                io.show_game_over("player_killed", "You were murdered by the werewolves in your sleep.")
                state.phase = GamePhase.GAME_OVER
                return

            result = state.check_win_condition()
            if result:
                io.show_game_over(result, WIN_MESSAGES[result])
                state.phase = GamePhase.GAME_OVER
                return
        else:
            io.show_system("The morning sun rises. Miraculously, everyone survived the night.", style="success")
            state.public_events.append(f"Night {state.day}: No one was killed.")
            state.main_topic = "No one died last night, but the killer is still out there."

    def _resolve_ga_protection(self) -> str | None:
        """Determines who the Guardian Angel protects tonight."""
        gm = self.gm
        state = gm.state

        ga_name = None
        for name in state.alive_characters:
            if state.roles.get(name) == "guardian_angel":
                ga_name = name
                break

        if not ga_name:
            return None

        valid_targets = [
            n for n in state.alive_characters
            if n != ga_name and n != state.ga_protected_last_night
        ]

        if not valid_targets:
            return None

        if ga_name == "Player":
            return self._player_ga_protect(valid_targets)
        else:
            return self._npc_ga_protect(ga_name, valid_targets)

    def _player_ga_protect(self, valid_targets: list[str]) -> str:
        """Menu for the player Guardian Angel to choose a protection target."""
        io = self.gm.io

        choice = io.prompt_menu(
            "Choose one person to protect from the werewolf tonight:",
            valid_targets,
            context="protect",
        )
        selected = valid_targets[choice]
        io.show_system(f"You watch over {selected} through the night.", style="accent")
        return selected

    def _npc_ga_protect(self, ga_name: str, valid_targets: list[str]) -> str:
        """NPC Guardian Angel chooses a protection target via stat engine."""
        gm = self.gm
        pref = gm.npc_controller.generate_protect_preference(ga_name, valid_targets)
        target = pref.get("target", None)

        if target and target in valid_targets:
            return target

        return random.choice(valid_targets) if valid_targets else None
