class IOHandler:
    """Abstracts all user-facing I/O so game logic can be tested and frontends swapped."""

    def display(self, text: str):
        print(text)

    def prompt(self, text: str) -> str:
        """Display a prompt and return user input."""
        return input(text)

    def pause(self, text: str = "\033[90m[Press Enter to continue] >\033[0m "):
        """Block until the user presses Enter."""
        input(text)
