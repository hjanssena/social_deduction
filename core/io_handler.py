import os
import re

from core.colors import RESET, paint_names

ANSI_ESCAPES = re.compile(r"\x1b\[[0-9;]*m")


class IOHandler:
    """Abstracts all user-facing I/O so game logic can be tested and frontends swapped.

    Structured methods (show_dialogue, show_vote, prompt_menu, etc.) provide typed
    data to the frontend.  The default implementations format text with ANSI colors
    and delegate to the three base methods.  Subclasses (e.g. a scripted test
    handler) can override the structured methods to capture typed data instead.
    """

    # Colors of the game's own messages (character colors come from core.colors)
    YELLOW, RED, GRAY, CYAN = "\033[93m", "\033[91m", "\033[90m", "\033[36m"

    def __init__(self):
        self.colors = {}  # {name: ansi escape}, set by the GameMaster
        self.no_color = bool(os.getenv("NO_COLOR"))

    def set_colors(self, colors: dict[str, str]):
        self.colors = colors

    def color_of(self, name: str) -> str:
        return self.colors.get(name, "")

    def paint(self, text: str, base: str = "") -> str:
        """`text` in the `base` color, with every character name in that character's color."""
        return f"{base}{paint_names(text, self.colors, base)}{RESET if base else ''}"

    def say(self, speaker: str, text: str, label: str = None):
        """`[label]: text`, all in the speaker's color. Other names in the label and text keep their own."""
        c = self.color_of(speaker)
        label = label or speaker
        return f"{self.paint(f'[{label}]:', c)} {c}{paint_names(text, self.colors, c)}{RESET if c else ''}"

    # ------------------------------------------------------------------
    # Base methods (CLI primitives)
    # ------------------------------------------------------------------

    def display(self, text: str):
        if getattr(self, "no_color", False):
            text = ANSI_ESCAPES.sub("", text)
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
        self.display(self.say(speaker, text, label=f"{speaker} -> {target}"))

    def show_reaction(self, speaker: str, target: str, text: str,
                      intent: str = None, emotion: str = None, intensity: str = None):
        """An NPC or player reaction to an assertion."""
        self.display(self.say(speaker, text, label=f"{speaker} -> {target}"))

    def show_reveal(self, speaker: str, role: str, text: str):
        """A role reveal announcement: the claim label in yellow, the words in the speaker's color."""
        self.display(f"\n{self.YELLOW}[Role claim: {role}]{RESET} " + self.say(speaker, text, label=f"{speaker} -> Room"))

    def show_report(self, speaker: str, role: str, text: str):
        """A morning report from a revealed role holder."""
        self.display(f"\n{self.YELLOW}[{role} report]{RESET} " + self.say(speaker, text))

    def show_primer(self, text: str):
        """Town Crier discussion primer at the start of each day."""
        self.display("\n" + self.paint(f"[Town Crier]: {text}", self.YELLOW) + "\n")

    def show_narration(self, text: str):
        """Prose narration (arrival scenes, atmospheric text)."""
        self.display(self.paint(text, self.CYAN))

    def show_system(self, text: str, style: str = "info"):
        """System messages. style: info, warning, error, muted."""
        colors = {"info": "\033[90m", "warning": "\033[93m", "error": "\033[91m",
                  "muted": "\033[90m", "success": "\033[92m", "special": "\033[95m",
                  "accent": "\033[94m"}
        c = colors.get(style, "\033[90m")
        self.display(self.paint(f"[System] {text}", c))

    def show_phase(self, name: str, day: int):
        """Phase transition header."""
        self.display(f"\n--- PHASE: {name} (DAY {day}) ---")

    def show_engine_debug(self, speaker: str, intent: str, target: str,
                          emotion: str, reasoning: str, intensity: str = None):
        """Debug output: the decision behind a line (intent, target, emotion, private thought)."""
        extra = f", {intensity}" if intensity else ""
        self.display("\n" + self.paint(
            f"[Logic ({speaker})]: [{intent}] -> {target} ({emotion}{extra}) | {reasoning}", self.GRAY))

    def show_vote(self, voter: str, target: str, thoughts: str = ""):
        """A single character's vote during the voting phase."""
        if thoughts:
            self.display(self.paint(f"[Thoughts ({voter})]: {thoughts}", self.GRAY))
        if target == "None":
            self.display(self.say(voter, "I... I cannot decide. I abstain."))
        else:
            self.display(self.say(voter, f"My vote is for {target}."))

    def show_death(self, name: str, cause: str, role: str = None):
        """A character has died (lynched or killed)."""
        if cause == "lynched":
            self.display("\n" + self.paint(f"The town has spoken. {name} is dragged to the gallows...", self.RED))
        else:
            self.display("\n" + self.paint(f"{name} was found dead — torn apart by werewolves.", self.RED))

    def show_final_words(self, speaker: str, text: str):
        """Condemned character's last words."""
        self.display(self.say(speaker, text))

    def show_game_over(self, result: str, message: str = ""):
        """Game over announcement."""
        self.display(message)

    def show_role_reveal_private(self, role: str, details: list[str] = None):
        """Reveal the player's secret role."""
        colors = {"werewolf": "\033[91m", "guardian_angel": "\033[94m",
                  "coroner": "\033[95m", "villager": "\033[92m"}
        c = colors.get(role, "")
        for line in (details or []):
            self.display(self.paint(line, c))

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
        self.display(self.paint(title))
        for i, opt in enumerate(options):
            self.display(f"[{i + 1}] " + self.paint(opt))
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
