"""Plays whole games with a scripted, nosy player and audits what the characters say against the truth.

The player asks the questions a real player would (who did you vote for, why did you vote for X,
who died, are you a wolf), plants false premises (a vote that never happened, a quote nobody said),
and then an LLM judge compares each answer, and each day's transcript, with the ground truth.

    uv run python scripts/probe.py --games 2 --turns 12
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
        if ("raise a new topic" in text or "make an assertion" in text or "join in" in text) \
                and s.day not in self.asserted_on:
            self.asserted_on.add(s.day)
            return self._false_quote()
        if "reaction to the verdict" in text and s.day not in self.aftermath_asked and s.last_verdict:
            self.aftermath_asked.add(s.day)
            hanged = s.last_verdict.get("hanged")
            if hanged:
                return self.probe("aftermath_votes", "Room",
                                  f"Which of you voted to hang {hanged}? Own it, and say why.")
        if "join in" in text and random.random() < 0.06:
            return self._ask_someone()
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

    def _ask_someone(self) -> str:
        """Joins the current topic by asking one villager something directly; they should answer next."""
        npcs = [n for n in self.gm.state.alive_characters if n != "Player"]
        who = random.choice(npcs)
        return self.probe("player_question", who, f"{who}, what were you doing when the body was found?")

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
        "aftermath_votes = asks the room who voted to hang the condemned; player_question = asks one villager "
        "directly, who should answer.\n\n"
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
# Discussion metrics: read from the transcript, so any version of the discussion can be compared
# ---------------------------------------------------------------------------

SPEECH = re.compile(r"^(?:\[Role claim: [^\]]+\] )?\[(\w+) -> (\w+)\]: (.+)$")
PLAIN = re.compile(r"\b(plain(ly)?|straight)\b", re.IGNORECASE)

STRUCTURE_JUDGE = (
    "You rate one day's discussion in a werewolf village game as a reader would experience it. "
    "structure, 1-5: 5 = a structured discussion that follows one line of inquiry about the killing, each line "
    "building on the ones before toward who did it; 3 = mostly coherent but jumping between points; 1 = scattered, "
    "people talking past each other and hopping between subjects. subjects: how many distinct subjects the day "
    "jumps between. Respond with JSON only."
)


def day_scenes(lines: list[str]) -> dict[int, str]:
    """{day: what the village woke up to}: the morning's crime scene (or quiet morning) text."""
    scenes, day, inside = {}, 0, False
    for line in lines:
        m = re.search(r"--- PHASE: (.*) \(DAY (\d+)\) ---", line)
        if m:
            inside, day = m.group(1) == "MORNING", int(m.group(2))
            continue
        if inside and line.strip() and not line.startswith(("[Logic", "[Press")):
            scenes[day] = (scenes.get(day, "") + " " + line.replace("[System] ", "")).strip()
    return scenes


TOPIC_JUDGE = (
    "You label every line of a group conversation. Lines are numbered. For each line decide:\n"
    "- reply: it responds to something said in the 3 lines right before it (answers, backs, challenges or "
    "follows up on it);\n"
    "- new_topic: it drops what was being discussed and brings up a different subject;\n"
    "- echo: it repeats a demand or point someone else made in the lines just before, adding nothing new "
    "(a pile-on: a third person asking the same question again);\n"
    "- non_sequitur: it answers a question nobody asked, misreads who said what, or makes no sense after "
    "the lines before it.\n"
    "Be strict: a line that merely mentions the same person but changes the subject is new_topic. "
    "Also mark each line on_theme: true if it is about the day's killing (the body, the crime scene and its "
    "traces, who could have done it, alibis, role claims, votes or reports as they bear on it); false if it "
    "is about something else (manners, old grudges, village business, the stranger's trade).\n"
    "Respond with JSON only."
)


def _grams(text: str, n: int = 4) -> set:
    words = re.findall(r"[a-z']+", text.lower())
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def echoes(text: str, earlier: str) -> bool:
    """True if `text` repeats a 4-word phrase of `earlier` (a pile-on: "what your own eyes saw")."""
    return bool(_grams(text) & _grams(earlier))


def discussion_days(lines: list[str]) -> dict[int, list[tuple[str, str, str, bool]]]:
    """{day: [(speaker, addressee, text, opens)]} for the spoken lines of each day's discussion. `opens` marks
    a line that starts a new round: an assertion in the old flow, a thread opener in the new one. The probe
    player's own lines are included as ("Player", "?", text, False): context for the judge, never counted."""
    days, day, inside, opening, player_opened = {}, 0, False, False, False
    for line in lines:
        m = re.search(r"--- PHASE: (.*) \(DAY (\d+)\) ---", line)
        if m:
            inside, day = m.group(1) == "DISCUSSION", int(m.group(2))
            continue
        if inside and "Discussion ended" in line:
            inside = False
        if re.search(r"\[System\] (Assertion \d+/\d+|— thread \d+:|— angle \d+:)", line):
            opening = not player_opened  # a thread the Player opened starts with their (uncounted) line
            player_opened = False
            continue
        probe = re.match(r"^\[probe:\w+\] (.+)$", line)
        if inside and probe:
            days.setdefault(day, []).append(("Player", "?", probe.group(1), False))
            opening, player_opened = False, True
            continue
        if inside and (sm := SPEECH.match(line)):
            days.setdefault(day, []).append((*sm.groups(), opening))
            opening = player_opened = False
    return days


def discussion_metrics(run: dict, llm=None) -> dict:
    days = discussion_days(run["lines"])
    scenes = day_scenes(run["lines"])
    npcs = set(run["final_truth"]["roles"]) - {"Player"}
    total = {"days": len(days), "lines": 0, "questions": 0, "unanswered": 0, "near_repeats": 0,
             "plain": 0, "openers": 0, "follow_ups": 0, "opener_replies": 0, "drift": 0, "echo": 0, "off_topic": 0, "off_theme": 0,
             "structure_sum": 0, "subjects_sum": 0, "rated_days": 0,
             "player_questions": 0, "player_answered": 0}
    for day, said in days.items():
        total["lines"] += sum(1 for w, *_ in said if w != "Player")
        for i, (who, to, text, _) in enumerate(said):
            if who == "Player":
                continue
            if to in npcs and "?" in text:
                total["questions"] += 1
                if not any(w == to for w, _, _, _ in said[i + 1:i + 4]):
                    total["unanswered"] += 1
            if any(w != who and echoes(text, t) for w, _, t, _ in said[max(0, i - 5):i]):
                total["near_repeats"] += 1
            total["plain"] += bool(PLAIN.search(text))
        if llm is not None and said:
            numbered = "\n".join(f"{n + 1}. [{w} -> {t}]: {x}" for n, (w, t, x, _) in enumerate(said))
            scene = scenes.get(day, "(unknown)")
            verdict = llm.generate_json(TOPIC_JUDGE, f"WHAT THE VILLAGE WOKE UP TO THIS MORNING:\n{scene}\n\n"
                                        f"CONVERSATION:\n{numbered}\n\n"
                                        'Return {"labels": [{"n": 1, "label": "reply|new_topic|echo|non_sequitur", '
                                        '"on_theme": true}, ...]} with one entry per line.') or {}
            rating = llm.generate_json(STRUCTURE_JUDGE, f"WHAT THE VILLAGE WOKE UP TO THIS MORNING:\n{scene}\n\n"
                                       f"CONVERSATION:\n{numbered}\n\n"
                                       'Return {"structure": <1-5>, "subjects": <number>}.') or {}
            if isinstance(rating.get("structure"), (int, float)):
                total["structure_sum"] += rating["structure"]
                total["subjects_sum"] += rating.get("subjects", 0) if isinstance(rating.get("subjects"), (int, float)) else 0
                total["rated_days"] += 1
            entries = {x.get("n"): x for x in verdict.get("labels", []) if isinstance(x, dict)}
            labels = {n: str(x.get("label", "")) for n, x in entries.items()}
            for n, (who, *_rest) in enumerate(said, start=1):
                if who != "Player" and entries.get(n, {}).get("on_theme") is False:
                    total["off_theme"] += 1
            for n, (who, _, _, opens) in enumerate(said, start=1):
                if who == "Player":
                    continue
                label = labels.get(n, "")
                total["openers" if opens else "follow_ups"] += 1
                if opens and label == "reply":
                    total["opener_replies"] += 1  # a new round that only keeps the last one going
                if not opens and label == "new_topic":
                    total["drift"] += 1  # a reply that wanders off to another subject
                total["off_topic"] += label == "non_sequitur"
                total["echo"] += label == "echo"
    for day_threads in run.get("threads", {}).values():
        for t in day_threads:
            turns = t["turns"]
            for i, turn in enumerate(turns):
                if turn["speaker"] == "Player" and turn["intent"] in ("question", "accuse") and turn["target"] in npcs:
                    total["player_questions"] += 1
                    total["player_answered"] += bool(i + 1 < len(turns) and turns[i + 1]["speaker"] == turn["target"])
    lines = max(1, total["lines"])
    total.update(lines_per_day=round(total["lines"] / max(1, total["days"]), 1),
                 unanswered_rate=round(total["unanswered"] / max(1, total["questions"]), 2),
                 repeat_rate=round(total["near_repeats"] / lines, 3),
                 plain_rate=round(total["plain"] / lines, 3),
                 opener_reply_rate=round(total["opener_replies"] / max(1, total["openers"]), 2),
                 drift_rate=round(total["drift"] / max(1, total["follow_ups"]), 3),
                 echo_rate=round(total["echo"] / lines, 3),
                 off_theme_rate=round(total["off_theme"] / lines, 3),
                 structure=round(total["structure_sum"] / max(1, total["rated_days"]), 2),
                 subjects_per_day=round(total["subjects_sum"] / max(1, total["rated_days"]), 1),
                 off_topic_rate=round(total["off_topic"] / lines, 3))
    return total


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
    threads = {str(day): [{"opener": t.opener, "topic": t.topic, "ended": t.ended, "owed": t.owed,
                           "turns": [vars(turn) for turn in t.turns]} for t in day_threads]
               for day, day_threads in gm.state.threads.items()}
    run = {"seed": seed, "log": path, "result": gm.state.game_result, "days": gm.state.day, "threads": threads,
           "minutes": round((time.time() - start) / 60, 1), "lines": io.lines, "probes": io.probes,
           "final_truth": io.truth(), "day_truth": io.day_truth}
    with open(path.replace(".log", ".json"), "w") as f:
        json.dump(run, f, indent=1)
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--turns", type=int, default=None, help="override spoken lines per day (turns_per_day)")
    parser.add_argument("--echo", action="store_true")
    parser.add_argument("--no-logic", action="store_true", help="hide [Logic] lines (what a player sees)")
    parser.add_argument("--audit", help="only re-judge a finished run's .json")
    parser.add_argument("--metrics", nargs="+", help="only print discussion metrics for finished runs' .json files")
    parser.add_argument("--no-topic-judge", action="store_true", help="metrics without the LLM off-topic check")
    parser.add_argument("--spare-player", action="store_true",
                        help="test only: the traveler is never hanged or killed, so games run longer")
    args = parser.parse_args()

    with open("config.json") as f:
        config = json.load(f)
    apply_env_overrides(config)
    config.setdefault("debug", {})["show_logic"] = not args.no_logic
    config["debug"]["show_threads"] = True
    if args.turns:
        config["discussion"]["turns_per_day"] = args.turns
    llm = create_llm(config)

    if args.metrics:
        judge = None if args.no_topic_judge else llm
        rows = []
        for path in args.metrics:
            with open(path) as f:
                run = json.load(f)
            rows.append({"seed": run["seed"], **discussion_metrics(run, judge)})
            print(json.dumps(rows[-1]), flush=True)
        keys = ("lines_per_day", "unanswered_rate", "repeat_rate", "plain_rate", "off_topic_rate")
        sums = {k: sum(r[k] for r in rows) for k in ("lines", "questions", "unanswered", "near_repeats", "plain",
                                                     "openers", "follow_ups", "opener_replies", "drift",
                                                     "echo", "off_topic", "off_theme", "structure_sum", "subjects_sum", "rated_days", "days", "player_questions", "player_answered")}
        print(json.dumps({"ALL": True, **sums,
                          "lines_per_day": round(sums["lines"] / max(1, sums["days"]), 1),
                          "unanswered_rate": round(sums["unanswered"] / max(1, sums["questions"]), 2),
                          "repeat_rate": round(sums["near_repeats"] / max(1, sums["lines"]), 3),
                          "plain_rate": round(sums["plain"] / max(1, sums["lines"]), 3),
                          "opener_reply_rate": round(sums["opener_replies"] / max(1, sums["openers"]), 2),
                          "drift_rate": round(sums["drift"] / max(1, sums["follow_ups"]), 3),
                          "echo_rate": round(sums["echo"] / max(1, sums["lines"]), 3),
                          "off_theme_rate": round(sums["off_theme"] / max(1, sums["lines"]), 3),
                          "structure": round(sums["structure_sum"] / max(1, sums["rated_days"]), 2),
                          "subjects_per_day": round(sums["subjects_sum"] / max(1, sums["rated_days"]), 1),
                          "off_topic_rate": round(sums["off_topic"] / max(1, sums["lines"]), 3)}))
        return

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
