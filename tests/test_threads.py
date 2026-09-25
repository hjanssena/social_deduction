"""Discussion threads: the thread model, the director, turn prompts and the thread-based discussion."""
from models.thread import Thread, Turn


def test_thread_tracks_who_owes_an_answer():
    t = Thread(day=1, opener="Garrick", topic="the wax at the mill gate")
    t.add(Turn("Garrick", "question", "Bram", "Bram, who lit the candle?"))
    assert t.owed == "Bram"
    t.add(Turn("Elias", "agree", "Garrick", "Aye, answer him."))
    assert t.owed == "Bram"  # agreeing doesn't settle it
    t.add(Turn("Bram", "defend_self", "None", "I was home."))
    assert t.owed is None
    t.add(Turn("Bram", "accuse", "Elias", "And you, Elias?"))
    assert t.owed == "Elias"


def test_passes_count_until_someone_speaks():
    t = Thread(day=1, opener="A")
    t.add_pass(); t.add_pass()
    assert t.passes_in_a_row == 2
    t.add(Turn("B", "neutral", "None", "Hm."))
    assert t.passes_in_a_row == 0


def test_render_and_summary():
    t = Thread(day=1, opener="Garrick", topic="the wax at the mill gate")
    t.add(Turn("Garrick", "question", "Bram", "Who lit it?"))
    t.add(Turn("Elias", "agree", "Garrick", "Answer him."))
    assert t.render() == "[Garrick -> Bram]: Who lit it?\n[Elias -> Garrick]: Answer him."
    assert t.summary() == ("Garrick raised the wax at the mill gate (Elias joined in). "
                           "Bram never answered Garrick.")
    assert t.participants() == ["Garrick", "Elias"] and t.turns_by("Garrick") == 1


def test_every_line_goes_into_the_chat_history_in_order(gm, llm, io):
    from core.phases.discussion import DiscussionPhase
    npcs = [n for n in gm.state.alive_characters if n != "Player"]
    a, b = npcs[:2]
    phase = DiscussionPhase(gm)
    phase._display_opening(a, {"intent": "accuse", "target": b, "dialogue": "You lie."})
    phase._display_turn(b, {"intent": "defend_self", "target": a, "dialogue": "I do not."})
    assert gm.state.chat_history[-2:] == [f"[{a} -> {b}]: You lie.", f"[{b} -> {a}]: I do not."]


# --- T2: the director ---------------------------------------------------------

import random as _random

from core.discussion_director import DiscussionDirector


def director(gm, seed=0, **cfg):
    gm.config.update(cfg)
    return DiscussionDirector(gm, rng=_random.Random(seed))


def npcs(gm):
    return [n for n in gm.state.alive_characters if n != "Player"]


def test_whoever_is_asked_answers_next(gm):
    d = director(gm)
    a, b = npcs(gm)[:2]
    t = Thread(day=1, opener=a)
    t.add(Turn(a, "question", b, "Where were you?"))
    assert d.next_speaker(t) == (b, "answer")


def test_answering_is_allowed_past_the_speaker_cap(gm):
    d = director(gm, max_turns_per_speaker=1)
    a, b = npcs(gm)[:2]
    t = Thread(day=1, opener=a)
    t.add(Turn(b, "neutral", "None", "Hm."))
    t.add(Turn(a, "accuse", b, "You!"))
    assert d.next_speaker(t) == (b, "answer")


def test_the_player_owes_one_answer_per_thread(gm):
    d = director(gm, bystander_chance=0)
    a = npcs(gm)[0]
    t = Thread(day=1, opener=a)
    t.add(Turn(a, "accuse", "Player", "The stranger did it."))
    assert d.next_speaker(t) == ("Player", "answer")
    t.player_prompted = True
    name, role = d.next_speaker(t)
    assert name != "Player"


def test_joiners_have_a_stake_and_are_not_the_last_speaker(gm):
    d = director(gm, bystander_chance=0)
    a, b = npcs(gm)[:2]
    t = Thread(day=1, opener=a)
    t.add(Turn(a, "neutral", "None", f"Has anyone seen {b} today?"))
    for seed in range(20):
        d.rng = _random.Random(seed)
        name, role = d.next_speaker(t)
        assert role == "join" and name != a and d.stake(name, t) > 0


def test_someone_named_in_the_last_line_has_a_stake(gm):
    d = director(gm)
    a, b = npcs(gm)[:2]
    t = Thread(day=1, opener=a)
    t.add(Turn(a, "neutral", "None", f"I trust {b} less every hour."))
    assert d.stake(b, t) == 2


def test_nobody_left_closes_the_thread(gm):
    d = director(gm, bystander_chance=0)
    a = npcs(gm)[0]
    for name in npcs(gm):  # nobody has feelings about anyone
        gm.state.logbooks[name].friends, gm.state.logbooks[name].enemies = [], []
        gm.state.logbooks[name].pack = []
    t = Thread(day=1, opener=a)
    t.add(Turn(a, "neutral", "None", "Cold morning."))
    assert d.next_speaker(t) == (None, "")


def test_those_who_passed_are_not_asked_again(gm):
    d = director(gm, bystander_chance=1)
    a = npcs(gm)[0]
    t = Thread(day=1, opener=a)
    t.add(Turn(a, "neutral", "None", "Cold morning."))
    for name in npcs(gm)[1:]:
        t.add_pass(name)
    assert d.next_speaker(t) == (None, "")


def test_closing_rules(gm):
    d = director(gm, max_turns_per_thread=3, turns_per_day=10)
    a, b = npcs(gm)[:2]
    t = Thread(day=1, opener=a)
    assert d.close_reason(t) == ""
    t.add_pass(); t.add_pass()
    assert d.close_reason(t) == "passes"
    for _ in range(3):
        t.add(Turn(a, "neutral", "None", "x"))
    assert d.close_reason(t) == "turns"
    d.turns_today = 10
    assert d.close_reason(Thread(day=1, opener=a)) == "budget" and not d.budget_left()


def test_accused_villagers_who_stayed_silent_are_likelier_to_open(gm):
    a, b = npcs(gm)[:2]
    gm.state.day = 1
    gm.record_action(a, "accuse", b, dialogue="You did it.")
    d = director(gm)
    assert d._accused_and_silent(b) and not d._accused_and_silent(a)
    gm.record_action(b, "defend_self", "None", dialogue="I did not.")
    assert not d._accused_and_silent(b)


def test_opener_decay(gm):
    d = director(gm, decay_factor=0.0)
    first = d.pick_opener()
    d.opened(first)
    assert all(d.pick_opener() != first for _ in range(20))


# --- T3: turn prompts and guards ------------------------------------------------

def open_thread(gm, a, b, dialogue="Where were you last night?", intent="question"):
    t = Thread(day=1, opener=a, topic="where people slept")
    t.add(Turn(a, intent, b, dialogue))
    return t


def test_open_prompt_lists_earlier_topics_and_asks_for_a_topic(gm, llm):
    a = npcs(gm)[0]
    llm.json_answers = [{"intent": "neutral", "dialogue": "The wax.", "topic": "the wax at the gate."}]
    r = gm.npc_controller.take_turn(a, "open", None, ["Bram raised the ink at the well."])
    prompt = llm.last_prompt
    assert "EARLIER TODAY:\n- Bram raised the ink at the well." in prompt
    assert '"topic"' in prompt and "THIS CONVERSATION" not in prompt
    assert r["topic"] == "the wax at the gate"


def test_answer_prompt_quotes_what_must_be_answered(gm, llm):
    a, b = npcs(gm)[:2]
    t = open_thread(gm, a, b)
    llm.json_answers = [{"intent": "defend_self", "dialogue": "Home, asleep."}]
    r = gm.npc_controller.take_turn(b, "answer", t, [])
    assert f'{a} just said to you: "Where were you last night?"' in llm.last_prompt
    assert f"THIS CONVERSATION (what is being discussed right now, in order):\n[{a} -> {b}]:" in llm.last_prompt
    assert r["dialogue"] == "Home, asleep."


def test_empty_answer_becomes_a_deflection(gm, llm):
    a, b = npcs(gm)[:2]
    r = gm.npc_controller.take_turn(b, "answer", open_thread(gm, a, b), [])
    assert r["intent"] == "deflect" and r["dialogue"]


def test_a_joiner_may_pass(gm, llm):
    a, b, c = npcs(gm)[:3]
    llm.json_answers = [{"intent": "pass", "dialogue": ""}]
    assert gm.npc_controller.take_turn(c, "join", open_thread(gm, a, b), []) is None
    assert "- pass: say nothing this time." in llm.last_prompt


def test_repeating_someone_elses_line_is_retried(gm, llm):
    a, b, c = npcs(gm)[:3]
    t = open_thread(gm, a, b, dialogue=f"{b}, tell us plainly what your own eyes saw.")
    llm.json_answers = [{"intent": "question", "target": b, "dialogue": f"{b}, tell us plainly what your own eyes saw!"},
                        {"intent": "agree", "target": a, "dialogue": "Aye, answer him."}]
    r = gm.npc_controller.take_turn(c, "join", t, [])
    assert f"{a} already said" in llm.last_prompt and r["dialogue"] == "Aye, answer him."


# --- T4: the thread-based discussion ------------------------------------------------

import re

from core.game_state import GamePhase
from core.phases.discussion import DiscussionPhase
from tests.conftest import FakeLLM


class ScriptedLLM(FakeLLM):
    """Answers by what the prompt asks for, so background prefetching can't reorder the answers."""

    def __init__(self, names, player_parse=None, join=None):
        super().__init__()
        self.names = names
        self.player_parse = player_parse or {"intent": "neutral", "target": "None"}
        self.join = join or (lambda speaker, prompt: {"intent": "pass", "dialogue": ""})

    def generate_json(self, system_prompt, user_prompt, *args, **kwargs):
        self.calls.append(("json", system_prompt, user_prompt))
        if user_prompt.startswith("Parse the player's text"):
            return dict(self.player_parse)
        speaker = re.match(r"You are (\w+)", system_prompt).group(1)
        other = next(n for n in self.names if n != speaker)
        if "THE FLOOR IS YOURS" in user_prompt:
            return {"intent": "question", "target": other, "dialogue": f"{other}, where were you?",
                    "topic": f"where {other} was"}
        if "just said to you" in user_prompt:
            return {"intent": "defend_self", "dialogue": f"{speaker} was at home."}
        if "may join this conversation" in user_prompt:
            return self.join(speaker, user_prompt)
        return {}


def run_day(gm, llm, **cfg):
    gm.llm = llm
    gm.state.day = 1
    gm.state.roles_known = True
    gm.config.update(cfg)
    gm.stat_engine.check_all_reveals = lambda: []
    DiscussionPhase(gm).run()
    return gm.state.threads[1]


def speech(io):
    return [re.sub(r"\x1b\[[0-9;]*m", "", l) for l in io.lines if "->" in l and not l.startswith("[Logic")]


def test_a_question_is_answered_next(gm, io):
    threads = run_day(gm, ScriptedLLM(npcs(gm)), turns_per_day=4)
    first = threads[0]
    asked = first.turns[0].target
    assert first.turns[1].speaker == asked and first.turns[1].dialogue == f"{asked} was at home."
    assert gm.state.phase == GamePhase.VOTING


def test_the_day_ends_when_the_turn_budget_runs_out(gm, io):
    threads = run_day(gm, ScriptedLLM(npcs(gm)), turns_per_day=5)
    assert 5 <= sum(len(t.turns) for t in threads) <= 6  # a last question may still get its answer
    assert threads[-1].ended == "budget"


def test_two_passes_close_a_thread(gm, io):
    threads = run_day(gm, ScriptedLLM(npcs(gm)), turns_per_day=2)
    assert threads[0].ended in ("passes", "no one left", "budget")
    assert all(len(t.turns) <= 2 for t in threads)


def test_every_line_reaches_the_chat_history_in_order(gm, io):
    threads = run_day(gm, ScriptedLLM(npcs(gm)), turns_per_day=4)
    lines = [l for l in gm.state.chat_history if not l.startswith("[Town Crier")]
    assert lines == [t.line() for th in threads for t in th.turns]


def test_the_players_question_is_answered_next(gm, io):
    names = npcs(gm)
    llm = ScriptedLLM(names)
    io.inputs = ["", "PLAYER_Q"]  # listen to the opener, then join in
    gm.llm = llm
    target_holder = {}

    def parse_for(prompt_owner=None):
        return {"intent": "question", "target": target_holder["t"], "summary": "asked"}

    original = gm.player_controller.process_reaction

    def process_reaction(text, *a, **k):
        opener = gm.state.threads[1][0].opener
        target_holder["t"] = next(n for n in names if n != opener and n != gm.state.threads[1][0].turns[0].target)
        llm.player_parse = parse_for()
        return original(text, *a, **k)

    gm.player_controller.process_reaction = process_reaction
    threads = run_day(gm, llm, turns_per_day=6)
    turns = threads[0].turns
    i = next(i for i, t in enumerate(turns) if t.speaker == "Player")
    assert turns[i].target == target_holder["t"] and turns[i + 1].speaker == target_holder["t"]


def test_a_role_claim_opens_a_thread(gm, io):
    llm = ScriptedLLM(npcs(gm))
    claimant = npcs(gm)[0]
    fired = []

    def reveals():
        if fired:
            return []
        fired.append(1)
        return [(claimant, {"claimed_role": "coroner"})]

    gm.npc_controller.generate_reveal = lambda name, result: {
        "intent": "reveal_role", "claimed_role": "coroner", "target": "None",
        "dialogue": "I am the Coroner.", "findings": []}
    gm.stat_engine.register_reveal = lambda *a: None
    gm.stat_engine.apply_reveal_pressure = lambda *a: None
    gm.stat_engine.process_duplicate_claim = lambda *a: None
    gm.llm = llm
    gm.state.day = 1
    gm.state.roles_known = True
    gm.config.update(turns_per_day=3)
    gm.stat_engine.check_all_reveals = reveals
    DiscussionPhase(gm).run()
    first = gm.state.threads[1][0]
    assert first.opener == claimant and first.turns[0].intent == "reveal_role"
    assert first.topic == "a claim to be the Coroner"


def test_a_silent_player_is_pressed_once_per_thread(gm, io):
    names = npcs(gm)

    class AccusePlayer(ScriptedLLM):
        def generate_json(self, system_prompt, user_prompt, *a, **k):
            if "THE FLOOR IS YOURS" in user_prompt:
                self.calls.append(("json", system_prompt, user_prompt))
                return {"intent": "accuse", "target": "Player", "dialogue": "The stranger did it.", "topic": "the stranger"}
            return super().generate_json(system_prompt, user_prompt, *a, **k)

    threads = run_day(gm, AccusePlayer(names), turns_per_day=2)
    out = "\n".join(io.lines)
    assert out.count("You refused to defend yourself") == len([t for t in threads if t.player_prompted])
    assert any(r["intent"] == "silent" for r in gm.state.public_record)


def test_show_threads_marks_topics(gm, io):
    gm.debug["show_threads"] = True
    run_day(gm, ScriptedLLM(npcs(gm)), turns_per_day=2)
    out = "\n".join(io.lines)
    assert "— thread 1: where" in out and "— closed (" in out


def test_a_last_question_still_gets_its_answer(gm):
    d = director(gm, max_turns_per_thread=2)
    a, b = npcs(gm)[:2]
    t = Thread(day=1, opener=a)
    t.add(Turn(a, "neutral", "None", "Cold."))
    t.add(Turn("Player", "question", b, "Where were you?"))
    assert d.close_reason(t) == "" and d.next_speaker(t) == (b, "answer")
    t.add(Turn(b, "question", a, "Why ask me?"))
    assert d.close_reason(t) == "turns"  # only one turn of overtime


def test_the_next_opener_knows_what_was_just_discussed(gm, io):
    llm = ScriptedLLM(npcs(gm))
    threads = run_day(gm, llm, turns_per_day=6)
    assert len(threads) >= 2
    opens = [c[2] for c in llm.calls if "THE FLOOR IS YOURS" in c[2]]
    assert f"The town has just finished with this: {threads[0].summary()}" in opens[1]
    assert threads[0].summary() in opens[1].split("EARLIER TODAY:")[1]


def test_an_opener_with_nothing_to_say_hands_the_floor_on(gm, io):
    names = npcs(gm)
    first = {}

    class Mute(ScriptedLLM):
        def generate_json(self, system_prompt, user_prompt, *a, **k):
            speaker = re.match(r"You are (\w+)", system_prompt).group(1)
            if "THE FLOOR IS YOURS" in user_prompt and not first:
                first["who"] = speaker
                self.calls.append(("json", system_prompt, user_prompt))
                return {"intent": "neutral", "dialogue": ""}
            return super().generate_json(system_prompt, user_prompt, *a, **k)

    threads = run_day(gm, Mute(names), turns_per_day=2)
    assert threads[0].opener != first["who"]
    assert "Glares" not in "\n".join(io.lines)


def test_a_speaker_sees_what_they_said_in_earlier_threads(gm, llm):
    a, b = npcs(gm)[:2]
    gm.state.day = 1
    gm.record_action(b, "defend_self", "None", dialogue="I never said I saw Maeve.")
    llm.json_answers = [{"intent": "defend_self", "dialogue": "As I said, no."}]
    gm.npc_controller.take_turn(b, "answer", open_thread(gm, a, b, dialogue="Did you see Maeve?"), [])
    assert 'WHAT YOU SAID EARLIER TODAY (stay consistent with it, or say why you changed your mind):\n- "I never said I saw Maeve."' in llm.last_prompt
