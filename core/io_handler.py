class IOHandler:
    """Abstracts all user-facing I/O so game logic can be tested and frontends swapped.

    Structured methods (show_dialogue, show_vote, prompt_menu, etc.) provide typed
    data to the frontend.  The default implementations format text with ANSI colors
    and delegate to the three base methods, keeping the CLI experience unchanged.
    Subclasses (e.g. ServerIOHandler) override the structured methods to produce
    typed events instead.
    """

    # ------------------------------------------------------------------
    # Base methods (CLI primitives)
    # ------------------------------------------------------------------

    def display(self, text: str):
        print(text, flush=True)

    def prompt(self, text: str) -> str:
        """Display a prompt and return user input."""
        return input(text)

    def pause(self, text: str = "\033[90m[Press Enter to continue] >\033[0m "):
        """Block until the user presses Enter."""
        input(text)

    # ------------------------------------------------------------------
    # Structured display methods
    # ------------------------------------------------------------------

    def show_dialogue(self, speaker: str, target: str, text: str,
                      intent: str = None, emotion: str = None):
        """An NPC or player assertion in the main discussion."""
        self.display(f"[{speaker} -> {target}]: {text}")

    def show_reaction(self, speaker: str, target: str, text: str,
                      intent: str = None, emotion: str = None, intensity: str = None):
        """An NPC or player reaction to an assertion."""
        self.display(f"[{speaker} -> {target}]: {text}")

    def show_reveal(self, speaker: str, role: str, text: str):
        """A role reveal announcement."""
        self.display(f"\n\033[93m[{speaker} -> Room]: {text}\033[0m")

    def show_report(self, speaker: str, role: str, text: str):
        """A morning report from a revealed role holder."""
        self.display(f"\n\033[93m[{speaker} ({role} Report)]: {text}\033[0m")

    def show_primer(self, text: str):
        """Town Crier discussion primer at the start of each day."""
        self.display(f"\n\033[93m[Town Crier]: {text}\033[0m\n")

    def show_narration(self, text: str):
        """Prose narration (prologue scenes, atmospheric text)."""
        self.display(f"\033[36m{text}\033[0m")

    def show_system(self, text: str, style: str = "info"):
        """System messages. style: info, warning, error, muted."""
        colors = {"info": "\033[90m", "warning": "\033[93m", "error": "\033[91m",
                  "muted": "\033[90m", "success": "\033[92m", "special": "\033[95m",
                  "accent": "\033[94m"}
        c = colors.get(style, "\033[90m")
        self.display(f"{c}[System] {text}\033[0m")

    def show_phase(self, name: str, day: int):
        """Phase transition header."""
        self.display(f"\n--- PHASE: {name} (DAY {day}) ---")

    def show_engine_debug(self, speaker: str, intent: str, target: str,
                          emotion: str, reasoning: str, intensity: str = None):
        """Debug output from the stat engine."""
        extra = f", {intensity}" if intensity else ""
        self.display(
            f"\n\033[90m[Engine ({speaker})]: [{intent}] -> {target} "
            f"({emotion}{extra}) | {reasoning}\033[0m"
        )

    def show_vote(self, voter: str, target: str, thoughts: str = ""):
        """A single character's vote during the voting phase."""
        if thoughts:
            self.display(f"\033[90m[Thoughts ({voter})]: {thoughts}\033[0m")
        if target == "None":
            self.display(f"[{voter}]: I... I cannot decide. I abstain.")
        else:
            self.display(f"[{voter}]: My vote is for {target}.")

    def show_death(self, name: str, cause: str, role: str = None):
        """A character has died (lynched or killed)."""
        if cause == "lynched":
            self.display(f"\n\033[91mThe town has spoken. {name} is dragged to the gallows...\033[0m")
        else:
            self.display(f"\n\033[91m{name} was found dead — torn apart by werewolves.\033[0m")

    def show_final_words(self, speaker: str, text: str):
        """Condemned character's last words."""
        self.display(f"[{speaker}]: {text}")

    def show_game_over(self, result: str, message: str = ""):
        """Game over announcement."""
        self.display(message)

    def show_role_reveal_private(self, role: str, details: list[str] = None):
        """Reveal the player's secret role at game start."""
        colors = {"werewolf": "\033[91m", "guardian_angel": "\033[94m",
                  "coroner": "\033[95m", "villager": "\033[92m"}
        c = colors.get(role, "\033[0m")
        for line in (details or []):
            self.display(f"{c}{line}\033[0m")

    # ------------------------------------------------------------------
    # Structured prompt methods
    # ------------------------------------------------------------------

    def prompt_assertion(self) -> str:
        """Prompt the player for an assertion (or Enter to skip)."""
        return self.prompt("[Press Enter to advance, or type to make an assertion] > ")

    def prompt_reaction(self, speaker: str) -> str:
        """Prompt the player for a reaction (or Enter to skip)."""
        return self.prompt(f"[Press Enter to advance, or type your reaction to {speaker}] > ")

    def prompt_reaction_forced(self, speaker: str) -> str:
        """Prompt when the player is directly accused."""
        return self.prompt(f"[You were accused! Type your reaction, or press Enter to stay silent] > ")

    def prompt_menu(self, title: str, options: list[str], context: str = "") -> int:
        """Show a numbered menu and return the selected index."""
        self.display(title)
        for i, opt in enumerate(options):
            self.display(f"[{i + 1}] {opt}")
        while True:
            try:
                choice = int(self.prompt("\n\033[90m[Enter the number of your choice] >\033[0m ")) - 1
                if 0 <= choice < len(options):
                    return choice
                self.display("\033[91mInvalid choice. Try again.\033[0m")
            except ValueError:
                self.display("\033[91mPlease enter a number.\033[0m")

    def prompt_final_words(self) -> str:
        """Prompt the condemned player for their last words."""
        return self.prompt("\033[93m[Speak your final words] >\033[0m ")
