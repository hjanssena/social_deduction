from core.game_state import GamePhase

ROLE_DISCOVERY = {
    "werewolf": "Tonight I learned the truth about myself: I am a werewolf. {pack}",
    "guardian_angel": "Tonight I learned I am the Guardian Angel: each night I can protect one person from the wolves.",
    "coroner": "Tonight I learned I am the Coroner: whenever someone is hanged, I will learn whether they were a werewolf.",
    "villager": "Tonight I learned I have no special gift. I am an ordinary villager, and I must find the wolves before they find me.",
}

PLAYER_BRIEFINGS = {
    "werewolf": [
        "You are a WEREWOLF.",
        "Goal: stay hidden, turn the town on itself, and hunt until the wolves equal the villagers.",
    ],
    "guardian_angel": [
        "You are the GUARDIAN ANGEL.",
        "From tomorrow night, you protect one person each night from the wolves.",
        "You cannot protect yourself, or the same person two nights in a row.",
        "Goal: keep the innocent alive and help the town find the werewolves.",
    ],
    "coroner": [
        "You are the CORONER.",
        "Whenever someone is hanged, you privately learn whether they were a werewolf.",
        "Goal: use what you learn to guide the town, without making yourself a target.",
    ],
    "villager": [
        "You are an INNOCENT VILLAGER.",
        "Goal: find the werewolves, convince the town, and vote to hang them before it's too late.",
    ],
}


class NightPhase:
    """Night: roles are learned (night 0), the Guardian Angel protects (from night 1) and the wolves hunt.
    Checks for game over when someone dies; otherwise hands over to the morning."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state

        io.show_phase("THE NIGHT", state.day)

        if not state.roles_known:
            self._learn_roles()

        first_night = state.day == 0
        alive_werewolves = [n for n in state.alive_characters if state.roles.get(n) == "werewolf"]
        candidates = [n for n in state.alive_characters if state.roles.get(n) != "werewolf"]
        if first_night:
            candidates = [n for n in candidates if n != "Player"]  # The Player can't be the first victim

        protected = None if first_night else self._resolve_ga_protection()
        target = self._resolve_kill(alive_werewolves, candidates)
        saved = bool(target) and target == protected

        state.attacked_last_night = target
        state.saved_last_night = target if saved else None
        state.ga_protected_last_night = protected
        if protected:
            note = " (nobody died, so I must have stopped the wolves)" if saved else ""
            state.ga_protection_history.append(f"Night {state.day}: Protected {protected}{note}")

        state.killed_last_night = []
        if target and not saved:
            state.alive_characters.remove(target)
            state.killed_last_night.append(target)
            state.public_events.append(f"Night {state.day}: {target} was killed by the werewolves.")
        else:
            state.public_events.append(f"Night {state.day}: No one was killed.")

        # Game over can't wait for the morning
        if target == "Player" and not saved:
            io.show_death("Player", "killed")
            gm.end_game("player_killed")
            return
        result = state.check_win_condition()
        if result:
            io.show_death(target, "killed")
            gm.end_game(result)
            return

        io.pause()
        state.day += 1
        state.phase = GamePhase.MORNING

    # ------------------------------------------------------------------
    # Night 0: everyone learns their own role
    # ------------------------------------------------------------------

    def _learn_roles(self):
        """Each character learns only their own role; wolves learn their pack, pinned as allies."""
        state = self.gm.state
        state.roles_known = True
        wolves = [n for n, r in state.roles.items() if r == "werewolf"]

        for name, book in state.logbooks.items():
            role = state.roles.get(name, "villager")
            pack_text = ""
            if role == "werewolf":
                book.assign_pack(wolves)
                pack_text = (f"My pack: {', '.join(book.pack)}. Whatever I thought of them before, we stand together now."
                             if book.pack else "I hunt alone.")
            book.add_entry(state.day, "Night", ROLE_DISCOVERY[role].format(pack=pack_text))

        self._brief_player(wolves)

    def _brief_player(self, wolves: list[str]):
        io = self.gm.io
        role = self.gm.state.roles.get("Player", "villager")
        lines = list(PLAYER_BRIEFINGS[role])
        if role == "werewolf":
            pack = [w for w in wolves if w != "Player"]
            lines.insert(1, f"Your pack: {', '.join(pack)}." if pack else "You are the lone werewolf.")
        io.show_system("As you lie awake, you realize what you are.", style="muted")
        io.show_role_reveal_private(role, lines)
        if self.gm.state.day == 0:
            io.show_system("Tonight, only the wolves hunt.", style="muted")
        io.pause()

    # ------------------------------------------------------------------
    # Wolves
    # ------------------------------------------------------------------

    def _resolve_kill(self, alive_werewolves, candidates) -> str | None:
        """Determines who the werewolves attack tonight."""
        gm = self.gm
        io = gm.io
        if not alive_werewolves or not candidates:
            return None

        if "Player" in alive_werewolves:
            return self._player_werewolf_kill(alive_werewolves, candidates)

        io.show_system("The village sleeps... but something evil stalks the night.", style="muted")
        decision = gm.npc_controller.decide_kill(alive_werewolves, candidates)
        gm.state.killer_last_night = decision["killer"]
        if gm.debug.get("show_logic"):
            io.show_engine_debug("Pack", "kill", decision["target"], "", decision["reasoning"])
        return decision["target"]

    def _player_werewolf_kill(self, alive_werewolves, candidates) -> str:
        """The NPC wolves whisper their suggestions; the player makes the final choice."""
        gm = self.gm
        io = gm.io

        npc_wolves = [w for w in alive_werewolves if w != "Player"]
        if npc_wolves:
            io.show_system("Your fellow werewolves whisper their desires in the dark...", style="muted")
            whispers = gm.npc_controller.decide_kill(alive_werewolves, candidates)["whispers"]
            for npc in npc_wolves:
                if npc in whispers:
                    io.show_dialogue(npc, "Pack", whispers[npc], intent="whisper")
        else:
            io.show_system("You are the lone werewolf. The choice is yours entirely.", style="error")

        gm.state.killer_last_night = "Player"
        return gm.player_controller.get_kill_target(candidates)

    # ------------------------------------------------------------------
    # Guardian Angel
    # ------------------------------------------------------------------

    def _resolve_ga_protection(self) -> str | None:
        """Determines who the Guardian Angel protects tonight."""
        state = self.gm.state
        ga_name = next((n for n in state.alive_characters if state.roles.get(n) == "guardian_angel"), None)
        if not ga_name:
            return None

        valid_targets = [n for n in state.alive_characters
                         if n != ga_name and n != state.ga_protected_last_night]
        if not valid_targets:
            return None
        if ga_name == "Player":
            return self._player_ga_protect(valid_targets)
        return self._npc_ga_protect(ga_name, valid_targets)

    def _player_ga_protect(self, valid_targets: list[str]) -> str:
        """Menu for the player Guardian Angel to choose a protection target."""
        io = self.gm.io
        choice = io.prompt_menu("Choose one person to protect from the werewolves tonight:",
                                valid_targets, context="protect")
        selected = valid_targets[choice]
        io.show_system(f"You watch over {selected} through the night.", style="accent")
        return selected

    def _npc_ga_protect(self, ga_name: str, valid_targets: list[str]) -> str:
        """NPC Guardian Angel chooses a protection target (LLM, engine fallback)."""
        gm = self.gm
        decision = gm.npc_controller.decide_protection(ga_name, valid_targets)
        if gm.debug.get("show_logic"):
            gm.io.show_engine_debug(ga_name, "protect", decision["target"], "", decision["thought_process"])
        return decision["target"]
