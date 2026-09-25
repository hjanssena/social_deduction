"""Per-character terminal colors.

Every character gets their own 256-color ANSI code, used for their name and their lines.
Colors reserved for the game's own messages are never handed out:
light yellow (Town Crier, info), red (deaths, errors), gray (system, logic), cyan (narration).
"""
import re

RESET = "\033[0m"
PLAYER_COLOR = "\033[1;97m"  # Bold white

# Well-separated hues, none close to the reserved yellow / red / gray / cyan
PALETTE = [75, 114, 141, 211, 215, 180, 176, 67, 107, 139, 110, 174]
# 256-color codes that look like the reserved message colors; never used for characters
RESERVED_256 = {11, 190, 191, 220, 221, 226, 227, 228, 229,   # yellow
                1, 9, 160, 196, 197, 203,                    # red
                7, 8, *range(232, 256),                      # gray
                6, 14, 30, 36, 37, 43, 44, 51, 80, 87}       # cyan


def ansi(code: int) -> str:
    return f"\033[38;5;{code}m"


def assign_colors(characters) -> dict[str, str]:
    """Returns {name: ansi escape}. A character's own `color` (a palette code) wins when it's
    free; everyone else gets the next unused palette color. The Player is bold white."""
    codes = {}
    for c in characters:
        code = getattr(c, "color", None)
        if code is not None and code not in codes.values():
            codes[c.name] = code
    free = [code for code in PALETTE if code not in codes.values()]
    for c in characters:
        if c.name not in codes:
            codes[c.name] = free.pop(0) if free else PALETTE[len(codes) % len(PALETTE)]
    colors = {name: ansi(code) for name, code in codes.items()}
    colors["Player"] = PLAYER_COLOR
    return colors


def paint_names(text: str, colors: dict[str, str], base: str = "") -> str:
    """Wraps every character name in `text` in that character's color, then resumes `base`."""
    if not colors or not text:
        return text
    names = sorted(colors, key=len, reverse=True)  # Longest first: "Sol Badguy" before "Sol"
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b")
    return pattern.sub(lambda m: f"{colors[m.group(1)]}{m.group(1)}{RESET}{base}", text)
