"""The casts the game can be played with. setup.cast in config.json (or the CAST environment variable)
picks one; RAW_CHARACTER_DATA is the default cast."""
from models.cast_crossover import RAW_CHARACTER_DATA as CROSSOVER
from models.cast_village import RAW_CHARACTER_DATA as VILLAGE

CASTS = {"crossover": CROSSOVER, "village": VILLAGE}
DEFAULT_CAST = "crossover"
RAW_CHARACTER_DATA = CASTS[DEFAULT_CAST]


def load_cast(config: dict) -> list[dict]:
    """The cast named by setup.cast (default: crossover)."""
    name = config.get("setup", {}).get("cast", DEFAULT_CAST)
    if name not in CASTS:
        raise ValueError(f"Unknown cast '{name}'. Use one of: {', '.join(CASTS)}.")
    return CASTS[name]
