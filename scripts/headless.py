"""Plays whole games against the configured LLM with no human input, for testing and balance.

The player presses Enter at every prompt (never speaks) and picks a random menu option.
Each game's full transcript is written to logs/headless/<timestamp>-seed<N>.log.

    uv run python scripts/headless.py --seed 3
    uv run python scripts/headless.py --games 5 --max-assertions 3
"""
import argparse
import json
import os
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_master import GameMaster  # noqa: E402
from core.io_handler import IOHandler  # noqa: E402
from main import apply_env_overrides  # noqa: E402
from models.character import Character  # noqa: E402
from models.characters_data import RAW_CHARACTER_DATA  # noqa: E402
from services.llm_factory import create_llm  # noqa: E402
from services.prompt_service import PromptService  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")


class HeadlessIO(IOHandler):
    """Writes everything to a log file (and optionally the terminal); never blocks."""

    def __init__(self, log_file, echo: bool):
        super().__init__()
        self.log_file = log_file
        self.echo = echo
        self.lines = []

    def display(self, text: str):
        plain = ANSI.sub("", text)
        self.lines.append(plain)
        self.log_file.write(plain + "\n")
        self.log_file.flush()
        if self.echo:
            print(text, flush=True)

    def prompt(self, text: str = "") -> str:
        return ""

    def pause(self, text: str = ""):
        pass

    def prompt_menu(self, title: str, options: list[str], context: str = "") -> int:
        self.display(title)
        choice = random.randrange(len(options))
        self.display(f"[headless picks] {options[choice]}")
        return choice


class TimedLLM:
    """Wraps the LLM service to count and time every call."""

    def __init__(self, llm):
        self.llm = llm
        self.times = []

    def _timed(self, fn, *args, **kwargs):
        start = time.time()
        try:
            return fn(*args, **kwargs)
        finally:
            self.times.append(time.time() - start)

    def generate_json(self, *args, **kwargs):
        return self._timed(self.llm.generate_json, *args, **kwargs)

    def generate_text(self, *args, **kwargs):
        return self._timed(self.llm.generate_text, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.llm, name)


def play(seed: int, config: dict, llm, echo: bool) -> dict:
    random.seed(seed)
    os.makedirs(os.path.join("logs", "headless"), exist_ok=True)
    path = os.path.join("logs", "headless", f"{datetime.now():%Y%m%d-%H%M%S}-seed{seed}.log")
    timed = TimedLLM(llm)
    start = time.time()
    with open(path, "w") as log_file:
        io = HeadlessIO(log_file, echo)
        chars = [Character(f"npc_{c['name'].lower()}", c) for c in RAW_CHARACTER_DATA]
        gm = GameMaster(timed, PromptService(), chars, config, io=io)
        io.display(f"ROLES: {gm.state.roles}")
        gm.run_loop()

    text = "\n".join(io.lines)
    won = {"village_wins": "village", "werewolves_win": "wolves", "player_killed": "player killed",
           "player_lynched": "player hanged"}.get(gm.state.game_result, "unfinished")
    return {
        "seed": seed,
        "winner": won,
        "days": gm.state.day,
        "calls": len(timed.times),
        "avg_call_s": round(sum(timed.times) / max(1, len(timed.times)), 1),
        "minutes": round((time.time() - start) / 60, 1),
        "fallbacks": text.count("fell back to the stat engine"),
        "abstains": text.count("I abstain"),
        "reveals": len(gm.state.revealed_roles),
        "log": path,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=None, help="seed of the first game (default: random)")
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--max-assertions", type=int, default=None, help="override assertions per day")
    parser.add_argument("--echo", action="store_true", help="also print the game to the terminal")
    args = parser.parse_args()

    with open("config.json") as f:
        config = json.load(f)
    apply_env_overrides(config)
    config.setdefault("debug", {})["show_logic"] = True
    if args.max_assertions:
        config["discussion"]["max_assertions_per_day"] = args.max_assertions

    llm = create_llm(config)
    first = args.seed if args.seed is not None else random.randrange(10_000)
    results = []
    for i in range(args.games):
        result = play(first + i, config, llm, args.echo)
        results.append(result)
        print(json.dumps(result), flush=True)

    if len(results) > 1:
        winners = Counter(r["winner"] for r in results)
        print(f"\n{len(results)} games: {dict(winners)}; "
              f"avg days {sum(r['days'] for r in results) / len(results):.1f}; "
              f"fallbacks {sum(r['fallbacks'] for r in results)}; "
              f"abstains {sum(r['abstains'] for r in results)}; "
              f"reveals {sum(r['reveals'] for r in results)}")


if __name__ == "__main__":
    main()
