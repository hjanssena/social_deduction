"""Plays whole games with a scripted, nosy player and audits what the characters say against the truth.

The player asks the questions a real player would (who did you vote for, why did you vote for X,
who died, are you a wolf), plants false premises (a vote that never happened, a quote nobody said),
and then an LLM judge compares each answer, and each day's transcript, with the ground truth.

    uv run python scripts/probe.py --games 2 --max-assertions 4
    uv run python scripts/probe.py --audit logs/probe/<run>.json   # re-judge a finished run

Transcripts and findings go to logs/probe/.
"""
import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_master import GameMaster  # noqa: E402
from main import apply_env_overrides  # noqa: E402
from models.character import Character  # noqa: E402
from models.characters_data import RAW_CHARACTER_DATA  # noqa: E402
from scripts.headless import ANSI, HeadlessIO  # noqa: E402
from services.llm_factory import create_llm  # noqa: E402
from services.prompt_service import PromptService  # noqa: E402

SAY = re.compile(r"\[Say something to (.+?)(?:, (\d) left)?, or press Enter")


class ProbeIO(HeadlessIO):
    """A player who talks: asks factual questions and plants false premises, logging each probe."""

    def __init__(self, log_file, echo):
        super().__init__(log_file, echo)
        self.gm = None
        self.probes = []
        self.asserted_on = set()
        self.aftermath_asked = set()
        self.day_truth = {}  # {day: truth as of the latest phase change that day}

    def display(self, text: str):
        super().display(text)
        if self.gm is not None and "--- PHASE:" in text:
            self.day_truth[str(self.gm.state.day)] = self.truth()

    # --- ground truth -------------------------------------------------------

    def truth(self) -> dict:
        s = self.gm.state
        return {
            "day": s.day,
            "phase": s.phase.name,
            "alive": list(s.alive_characters),
            "roles": dict(s.roles),
            "public_events": list(s.public_events),
            "votes_today": s.votes_by_day.get(s.day, {}),
            "votes_by_day": {str(k): v for k, v in s.votes_by_day.items()},
            "role_claims": dict(s.revealed_roles),
            "evidence": s.clues.render_public(),
            "player_said": [e["dialogue"] for e in s.public_record if e.get("speaker") == "Player"],
        }

    def probe(self, kind: str, listener: str, question: str) -> str:
        self.probes.append({"kind": kind, "listener": listener, "question": question,
                            "line": len(self.lines), "truth": self.truth()})
        self.display(f"[probe:{kind}] {question}")
        return question

    # --- scripted answers ---------------------------------------------------

    def prompt(self, text: str = "") -> str:
        text = ANSI.sub("", text)
        if self.gm is None or not self.gm.state.roles_known and "Say something" not in text:
            return ""
        s = self.gm.state
        m = SAY.search(text)
        if m:
            return self._say(m.group(1), int(m.group(2)) if m.group(2) else None)
        if "make an assertion" in text and s.day not in self.asserted_on:
            self.asserted_on.add(s.day)
            return self._false_quote()
        if "reaction to the verdict" in text and s.day not in self.aftermath_asked and s.last_verdict:
            self.aftermath_asked.add(s.day)
            hanged = s.last_verdict.get("hanged")
            if hanged:
                return self.probe("aftermath_votes", "Room",
                                  f"Which of you voted to hang {hanged}? Own it, and say why.")
        if "You were accused" in text or ("reaction to" in text and random.random() < 0.15):
            return random.choice(["I only just arrived in this village. Why on earth would it be me?",
                                  "I was asleep upstairs at the tavern all night. Ask the keeper.",
                                  "Look at the evidence, not at the stranger."])
        if "final words" in text:
            return "You're hanging the wrong person."
        return ""

    def _say(self, listener: str, left: int | None) -> str:
        s = self.gm.state
        others = [n for n in s.alive_characters if n not in (listener, "Player")]
        if left is None:  # introductions: sometimes silent, to exercise the silence remarks
            return random.choice(["", "", "Just a merchant passing through.", "Name's Rowan. I sell cloth.",
                                  "Evening. What's got everyone so jumpy?"])
        ballots = s.votes_by_day.get(s.day, {})
        mine = ballots.get(listener)
        if left == 3:
            if not ballots:
                return self.probe("false_vote", listener,
                                  f"Why did you vote to hang me today, {listener}?")
            if random.random() < 0.5:
                return self.probe("own_vote", listener, "Who did you vote for today, and why?")
            wrong = [n for n in ballots if n not in (mine, listener)] or others
            return self.probe("false_vote", listener,
                              f"Why did you vote for {random.choice(wrong)} today? I saw you.")
        if left == 2:
            return self.probe("memory", listener,
                              "Remind me: who has died so far, and how? And what has the Coroner told us?")
        wolves = [n for n, r in s.roles.items() if r == "werewolf" and n != listener]
        if s.roles.get(listener) == "werewolf":
            return self.probe("secret", listener,
                              f"Just between us: are you one of them? Is {random.choice(wolves or others)} with you?")
        return self.probe("secret", listener, "Just between us, what is your real role here? Who do you trust?")

    def _false_quote(self) -> str:
        s = self.gm.state
        npcs = [n for n in s.alive_characters if n != "Player"]
        if len(npcs) < 2:
            return ""
        quoted, accused = random.sample(npcs, 2)
        return self.probe("false_quote", quoted,
                          f"{quoted}, earlier you told me you saw {accused} near the body before dawn. "
                          f"Tell everyone what you saw.")


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = (
    "You audit a werewolf social-deduction game run by an AI. Characters are AI-played villagers. "
    "Your job is to find CONSISTENCY BUGS: a character stating something that contradicts the ground truth "
    "they could know. Do not flag lies that are strategic for the speaker's side (a werewolf lying about "
    "suspicions or fake-claiming a role is fine; a werewolf pretending to be a villager is expected). "
    "Do flag: a character misstating their OWN public actions (their vote, what they said), misstating "
    "public facts everyone saw (who died, who was hanged, how people voted, what the evidence is), "
    "treating a dead character as alive, accepting a false premise the player planted instead of "
    "correcting it, inventing events that never happened as if everyone witnessed them, a werewolf "
    "revealing themselves or their packmates to a non-wolf, anyone revealing a secret role outside a "
    "deliberate public claim, and misattributing who said what. "
    "Be strict about facts but do not nitpick tone or opinions. Respond with JSON only."
)


def judge_probe(llm, probe: dict, answer: list[str]) -> dict:
    t = probe["truth"]
    who = probe["listener"]
    prompt = (
        f"GROUND TRUTH (day {t['day']}, phase {t['phase']}):\n"
        f"Alive: {', '.join(t['alive'])}\n"
        f"Secret roles: {json.dumps(t['roles'])}\n"
        f"Public events: {json.dumps(t['public_events'])}\n"
        f"Votes by day: {json.dumps(t['votes_by_day'])}\n"
        f"Public role claims: {json.dumps(t['role_claims'])}\n"
        f"Public evidence: {t['evidence'] or '(none)'}\n"
        f"Everything the player (the traveler) has said in public: {json.dumps(t['player_said'])}\n\n"
        f"PROBE ({probe['kind']}): the player said to {who}: \"{probe['question']}\"\n"
        "Probe kinds: own_vote = asks their vote; false_vote = asserts a vote that did NOT happen "
        "(check Votes by day); memory = asks who died and what the Coroner said; secret = fishes for a "
        "hidden role; false_quote = claims the character said something they never said; "
        "aftermath_votes = asks the room who voted to hang the condemned.\n\n"
        "WHAT FOLLOWED:\n" + "\n".join(answer) + "\n\n"
        'Return {"issues": [{"speaker": name, "type": "own_action|public_fact|false_premise|dead_alive|'
        'invented_event|secret_leak|misattribution", "quote": exact words, "truth": what is actually '
        'true, "severity": "high|medium|low"}]}. An empty list if everything is consistent.'
    )
    return llm.generate_json(JUDGE_SYSTEM, prompt) or {"issues": [], "error": "no judge answer"}


def judge_day(llm, day: int, truth: dict, transcript: list[str]) -> dict:
    prompt = (
        f"GROUND TRUTH at the end of day {day}:\n"
        f"Secret roles: {json.dumps(truth['roles'])}\n"
        f"Public events: {json.dumps(truth['public_events'])}\n"
        f"Votes by day: {json.dumps(truth['votes_by_day'])}\n"
        f"Public role claims: {json.dumps(truth['role_claims'])}\n"
        f"Public evidence: {truth['evidence'] or '(none)'}\n\n"
        "TRANSCRIPT OF THE DAY (lines starting [Logic] and [probe:...] are hidden debug notes, not "
        "speech; [X -> Player] in the EVENING phase is a private talk only the player hears):\n"
        + "\n".join(transcript) + "\n\n"
        "Find every consistency bug in what characters SAY. Also flag a character contradicting "
        "something they themselves said earlier the same day without explanation. "
        'Return {"issues": [{"speaker": name, "type": "own_action|public_fact|false_premise|dead_alive|'
        'invented_event|secret_leak|misattribution|self_contradiction", "quote": exact words, '
        '"truth": what is actually true, "severity": "high|medium|low"}]}.'
    )
    return llm.generate_json(JUDGE_SYSTEM, prompt) or {"issues": [], "error": "no judge answer"}


def answers_for(lines: list[str], probe: dict, next_line: int) -> list[str]:
    """The lines that followed a probe, up to the next probe (at most 14 lines of speech)."""
    out = []
    for line in lines[probe["line"]:next_line]:
        if line.startswith(("[Logic", "[Press", "[headless")) or not line.strip():
            continue
        out.append(line)
        if len(out) >= 14:
            break
    return out


def split_days(lines: list[str]) -> dict[int, list[str]]:
    days, current = {}, 0
    for line in lines:
        m = re.search(r"--- PHASE: .* \(DAY (\d+)\) ---", line)
        if m:
            current = int(m.group(1))
        if line.startswith("[Logic"):
            continue
        days.setdefault(current, []).append(line)
    return days


def audit(llm, run: dict) -> dict:
    lines, probes = run["lines"], run["probes"]
    findings = []
    for i, p in enumerate(probes):
        nxt = probes[i + 1]["line"] if i + 1 < len(probes) else len(lines)
        answer = answers_for(lines, p, nxt)
        verdict = judge_probe(llm, p, answer)
        for issue in verdict.get("issues", []):
            findings.append({"source": f"probe:{p['kind']}", "day": p["truth"]["day"],
                             "question": p["question"], **issue})
    for day, transcript in split_days(lines).items():
        truth = run.get("day_truth", {}).get(str(day)) or run["final_truth"]  # as of that evening
        verdict = judge_day(llm, day, truth, transcript)
        for issue in verdict.get("issues", []):
            findings.append({"source": "day_audit", "day": day, **issue})
    return {"seed": run["seed"], "log": run["log"], "findings": findings}


# ---------------------------------------------------------------------------

def spare_player(gm):
    """Test-only: keeps the traveler alive so later days (and evening chats after a vote) get probed.
    NPC votes for the Player become abstentions; the wolves never pick the Player as a victim."""
    npc = gm.npc_controller
    decide_votes, decide_kill = npc.decide_votes, npc.decide_kill

    def votes(voters):
        result = decide_votes(voters)
        for v in result.values():
            if v.get("target") == "Player":
                v.update(target="None", says="")
        return result

    def kill(wolves, candidates):
        return decide_kill(wolves, [c for c in candidates if c != "Player"] or candidates)

    npc.decide_votes, npc.decide_kill = votes, kill


def play(seed: int, config: dict, llm, echo: bool, spare: bool = False) -> dict:
    random.seed(seed)
    os.makedirs(os.path.join("logs", "probe"), exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}-seed{seed}"
    path = os.path.join("logs", "probe", f"{stamp}.log")
    start = time.time()
    with open(path, "w") as log_file:
        io = ProbeIO(log_file, echo)
        chars = [Character(f"npc_{c['name'].lower()}", c) for c in RAW_CHARACTER_DATA]
        gm = GameMaster(llm, PromptService(), chars, config, io=io)
        io.gm = gm
        if spare:
            spare_player(gm)
        io.display(f"ROLES: {gm.state.roles}")
        gm.run_loop()
    run = {"seed": seed, "log": path, "result": gm.state.game_result, "days": gm.state.day,
           "minutes": round((time.time() - start) / 60, 1), "lines": io.lines, "probes": io.probes,
           "final_truth": io.truth(), "day_truth": io.day_truth}
    with open(path.replace(".log", ".json"), "w") as f:
        json.dump(run, f, indent=1)
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--max-assertions", type=int, default=None)
    parser.add_argument("--echo", action="store_true")
    parser.add_argument("--no-logic", action="store_true", help="hide [Logic] lines (what a player sees)")
    parser.add_argument("--audit", help="only re-judge a finished run's .json")
    parser.add_argument("--spare-player", action="store_true",
                        help="test only: the traveler is never hanged or killed, so games run longer")
    args = parser.parse_args()

    with open("config.json") as f:
        config = json.load(f)
    apply_env_overrides(config)
    config.setdefault("debug", {})["show_logic"] = not args.no_logic
    if args.max_assertions:
        config["discussion"]["max_assertions_per_day"] = args.max_assertions
    llm = create_llm(config)

    runs = []
    if args.audit:
        with open(args.audit) as f:
            runs.append(json.load(f))
    else:
        first = args.seed if args.seed is not None else random.randrange(10_000)
        for i in range(args.games):
            run = play(first + i, config, llm, args.echo, args.spare_player)
            print(json.dumps({k: run[k] for k in ("seed", "result", "days", "minutes", "log")}), flush=True)
            runs.append(run)

    for run in runs:
        report = audit(llm, run)
        out = run["log"].replace(".log", ".findings.json")
        with open(out, "w") as f:
            json.dump(report, f, indent=1)
        high = sum(1 for x in report["findings"] if x.get("severity") == "high")
        print(json.dumps({"seed": run["seed"], "findings": len(report["findings"]), "high": high,
                          "report": out}), flush=True)


if __name__ == "__main__":
    main()
