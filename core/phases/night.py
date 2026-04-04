import random
from collections import Counter

from core.game_state import GamePhase


class NightPhase:
    """Handles win-condition checks, werewolf kill selection, and kill execution."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state

        io.display("\n\033[36m" + "="*50)
        io.display("                 THE NIGHT PHASE")
        io.display("="*50 + "\033[0m\n")

        alive_werewolves = [name for name in state.alive_characters if state.roles.get(name) == "werewolf"]
        alive_villagers = [name for name in state.alive_characters if state.roles.get(name) != "werewolf"]

        if self._check_win_conditions(alive_werewolves, alive_villagers):
            return

        killed_target = self._resolve_kill(alive_werewolves, alive_villagers)
        self._execute_kill(killed_target)

    def _check_win_conditions(self, alive_werewolves, alive_villagers) -> bool:
        """Returns True if the game is over."""
        io = self.gm.io
        state = self.gm.state

        if len(alive_werewolves) == 0:
            io.display("\n\033[92m[VICTORY] All werewolves have been eliminated! The village is safe.\033[0m")
            state.phase = GamePhase.GAME_OVER
            return True

        if len(alive_werewolves) >= len(alive_villagers):
            io.display("\n\033[91m[DEFEAT] The werewolves now outnumber the villagers. The town falls to the beasts.\033[0m")
            state.phase = GamePhase.GAME_OVER
            return True

        return False

    def _resolve_kill(self, alive_werewolves, alive_villagers) -> str:
        """Determines who the werewolves kill tonight."""
        gm = self.gm
        io = gm.io

        if "Player" in alive_werewolves:
            return self._player_werewolf_kill(alive_werewolves, alive_villagers)

        io.display("\033[90m[System] The village sleeps... but something evil stalks the night.\033[0m")

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
            io.display("\033[90m[System] Your fellow werewolves whisper their desires in the dark...\033[0m")
            for npc in npc_wolves:
                pref = gm.npc_controller.generate_kill_preference(npc, alive_villagers)
                io.display(
                    f"\033[91m[{npc} (Whisper)]: {pref['thought_process']} "
                    f"-> (Wants to kill {pref['target']})\033[0m"
                )
        else:
            io.display("\033[91m[System] You are the lone werewolf. The choice is yours entirely.\033[0m")

        return gm.player_controller.get_kill_target(alive_villagers)

    def _execute_kill(self, killed_target):
        """Applies the kill to game state and checks for player death."""
        gm = self.gm
        io = gm.io
        state = gm.state

        state.killed_last_night = []

        if killed_target and killed_target != "None":
            io.display(
                f"\n\033[91m[System] Screams shatter the morning silence. "
                f"{killed_target} has been murdered!\033[0m"
            )

            state.alive_characters.remove(killed_target)
            state.killed_last_night.append(killed_target)
            state.public_events.append(
                f"Night {state.day}: {killed_target} was brutally killed by the werewolves."
            )

            if killed_target == "Player":
                io.display("\n\033[91m[GAME OVER] You were murdered by the werewolves in your sleep.\033[0m")
                state.phase = GamePhase.GAME_OVER
                return
        else:
            io.display("\n\033[92m[System] The morning sun rises. Miraculously, everyone survived the night.\033[0m")
            state.public_events.append(f"Night {state.day}: No one was killed.")

        io.pause("\n\033[90m[Press Enter to start the next day] >\033[0m ")

        state.day += 1
        state.phase = GamePhase.DISCUSSION
