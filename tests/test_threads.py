"""The day's discussion: one conversation about the killing. The thread model, the director, the turn
prompts and the discussion phase."""
import random as _random
import re

from core.discussion_director import DiscussionDirector
from core.game_state import GamePhase
from core.phases.discussion import DiscussionPhase
from models.thread import Thread, Turn
from tests.conftest import FakeLLM

THEME = "Who killed Silas last night? Silas was found at the mill race, with traces of wax beside the body."


def npcs(gm):
    return [n for n in gm.state.alive_characters if n != "Player"]


def director(gm, seed=0, **cfg):
    gm.config.update(cfg)
    return DiscussionDirector(gm, rng=_random.Random(seed))


def thread_with(*turns):
    t = Thread(day=1, opener=turns[0][0] if turns else "")
    for speaker, intent, target, dialogue in turns:
        t.add(Turn(speaker, intent, target, dialogue))
    return t


# --- the thread model -------------------------------------------------------------

def test_thread_tracks_who_owes_an_answer():
    t = thread_with(("Garrick", "question", "Bram", "Bram, who lit the candle?"))
    assert t.owed == "Bram"
    t.add(Turn("Elias", "agree", "Garrick", "Aye, answer him."))
    assert t.owed == "Bram"  # agreeing doesn't settle it
    t.add(Turn("Bram", "defend_self", "None", "I was home."))
    assert t.owed is None
    t.add(Turn("Bram", "accuse", "Elias", "And you, Elias?"))
    assert t.owed == "Elias"


def test_a_spoken_line_clears_the_passes():
    t = thread_with(("A", "neutral", "None", "Hm."))
    t.add_pass("B"); t.add_pass("C")
    assert t.passes_in_a_row == 2 and t.passed == {"B", "C"}
    t.add(Turn("D", "neutral", "None", "Well."))
    assert t.passes_in_a_row == 0 and not t.passed


def test_render():
    t = thread_with(("Garrick", "question", "Bram", "Who lit it?"), ("Elias", "agree", "Garrick", "Answer him."))
    assert t.render() == "[Garrick -> Bram]: Who lit it?\n[Elias -> Garrick]: Answer him."


# --- the director -------------------------------------------------------------------

def test_someone_opens_the_day(gm):
    name, role = director(gm).next_speaker(Thread(day=1, opener=""))
    assert role == "lead" and name in npcs(gm)


def test_whoever_is_asked_answers_next(gm):
    a, b = npcs(gm)[:2]
    assert director(gm).next_speaker(thread_with((a, "question", b, "Where were you?"))) == (b, "answer")


def test_answers_are_exempt_from_the_speaker_window(gm):
    a, b = npcs(gm)[:2]
    t = thread_with((b, "neutral", "None", "Hm."), (b, "neutral", "None", "Hm!"), (a, "accuse", b, "You!"))
    assert director(gm, max_in_window=2).next_speaker(t) == (b, "answer")


def test_the_player_owes_an_answer(gm):
    a = npcs(gm)[0]
    t = thread_with((a, "accuse", "Player", "The stranger did it."))
    d = director(gm)
    assert d.next_speaker(t) == ("Player", "answer")
    t.player_prompted = True
    assert d.next_speaker(t)[0] != "Player"


def test_responders_have_a_stake_in_the_last_two_lines(gm):
    a, b, c = npcs(gm)[:3]
    t = thread_with((c, "neutral", "None", "Cold morning."), (a, "neutral", "None", f"Has anyone seen {b} today?"))
    for seed in range(20):
        d = director(gm, seed=seed, bystander_chance=0)
        name, role = d.next_speaker(t)
        assert name != a and (role == "lead" or d.stake(name, t) > 0)
    assert director(gm).stake(b, t) == 2


def test_the_speaker_window_keeps_one_voice_from_taking_over(gm):
    a, b = npcs(gm)[:2]
    t = thread_with((b, "neutral", "None", f"{a}?"), (a, "neutral", "None", "Hm."), (b, "neutral", "None", f"{a}!"),
                    (a, "neutral", "None", "Hm!"))
    d = director(gm, max_in_window=2, speaker_window=6, bystander_chance=0)
    assert not d._room_to_speak(a, t) and not d._room_to_speak(b, t)


def test_two_passes_move_the_discussion_on(gm):
    a, b, c = npcs(gm)[:3]
    t = thread_with((a, "neutral", "None", "Cold morning."))
    t.add_pass(b); t.add_pass(c)
    name, role = director(gm).next_speaker(t)
    assert role == "lead" and name != a


def test_nobody_with_a_stake_moves_it_on(gm):
    a = npcs(gm)[0]
    for name in npcs(gm):
        book = gm.state.logbooks[name]
        book.friends, book.enemies, book.pack = [], [], []
    t = thread_with((a, "neutral", "None", "Cold morning."))
    name, role = director(gm, bystander_chance=0).next_speaker(t)
    assert role == "lead" and name != a


def test_the_day_ends_on_its_budget_but_a_last_question_is_answered(gm):
    a, b = npcs(gm)[:2]
    d = director(gm, turns_per_day=2)
    t = thread_with((a, "neutral", "None", "Cold."), ("Player", "question", b, "Where were you?"))
    d.turns_today = 2
    assert not d.day_over(t) and d.next_speaker(t) == (b, "answer")
    t.add(Turn(b, "question", a, "Why ask me?"))
    assert d.day_over(t)  # only one turn of overtime


def test_accused_villagers_who_stayed_silent_are_likelier_to_lead(gm):
    a, b = npcs(gm)[:2]
    gm.state.day = 1
    gm.record_action(a, "accuse", b, dialogue="You did it.")
    d = director(gm)
    assert d._accused_and_silent(b) and not d._accused_and_silent(a)
    gm.record_action(b, "defend_self", "None", dialogue="I did not.")
    assert not d._accused_and_silent(b)


def test_leading_decays(gm):
    d = director(gm, decay_factor=0.0)
    first = d.pick_lead()
    d.led(first)
    assert all(d.pick_lead() != first for _ in range(20))


# --- turn prompts and guards ----------------------------------------------------------

def test_every_prompt_leads_with_the_days_question_and_the_last_two_lines(gm, llm):
    a, b, c = npcs(gm)[:3]
    t = thread_with((a, "neutral", "None", "First, old line."), (b, "neutral", "None", "Second line."),
                    (a, "question", c, "Third line?"))
    llm.json_answers = [{"intent": "agree", "target": a, "dialogue": "Aye."}]
    gm.npc_controller.take_turn(c, "join", t, THEME)
    p = llm.last_prompt
    assert f"TODAY'S QUESTION (the whole discussion is about this):\n{THEME}" in p
    assert f"EARLIER IN TODAY'S DISCUSSION (for reference):\n[{a} -> Room]: First, old line." in p
    assert f"JUST SAID (respond to this):\n[{b} -> Room]: Second line.\n[{a} -> {c}]: Third line?" in p
    assert "Every line is about TODAY'S QUESTION" in p


def test_the_opening_line_starts_with_the_killing(gm, llm):
    llm.json_answers = [{"intent": "neutral", "dialogue": "The wax.", "angle": "the wax by the body."}]
    r = gm.npc_controller.take_turn(npcs(gm)[0], "lead", Thread(day=1, opener=""), THEME)
    assert "opens today's discussion. Start with the killing itself" in llm.last_prompt
    assert "JUST SAID" not in llm.last_prompt and r["topic"] == "the wax by the body"


def test_a_lead_moves_it_on_from_what_was_just_said(gm, llm):
    a, b = npcs(gm)[:2]
    llm.json_answers = [{"intent": "question", "target": a, "dialogue": "And the wax?", "angle": "the wax"}]
    gm.npc_controller.take_turn(b, "lead", thread_with((a, "neutral", "None", "The boots prove nothing.")), THEME)
    assert "bring up one angle of the killing nobody has covered yet" in llm.last_prompt
    assert "JUST SAID (respond to this):" in llm.last_prompt


def test_answer_prompt_quotes_what_must_be_answered(gm, llm):
    a, b = npcs(gm)[:2]
    llm.json_answers = [{"intent": "defend_self", "dialogue": "Home, asleep."}]
    r = gm.npc_controller.take_turn(b, "answer", thread_with((a, "question", b, "Where were you last night?")), THEME)
    assert f'{a} just said to you: "Where were you last night?"' in llm.last_prompt
    assert r["dialogue"] == "Home, asleep."


def test_empty_answer_becomes_a_deflection(gm, llm):
    a, b = npcs(gm)[:2]
    r = gm.npc_controller.take_turn(b, "answer", thread_with((a, "question", b, "Where?")), THEME)
    assert r["intent"] == "deflect" and r["dialogue"]


def test_a_joiner_may_pass(gm, llm):
    a, b, c = npcs(gm)[:3]
    llm.json_answers = [{"intent": "pass", "dialogue": ""}]
    assert gm.npc_controller.take_turn(c, "join", thread_with((a, "question", b, "Where?")), THEME) is None
    assert "- pass: say nothing this time." in llm.last_prompt


def test_repeating_someone_elses_line_is_retried(gm, llm):
    a, b, c = npcs(gm)[:3]
    t = thread_with((a, "question", b, f"{b}, tell us plainly what your own eyes saw."))
    llm.json_answers = [{"intent": "question", "target": b, "dialogue": f"{b}, tell us plainly what your own eyes saw!"},
                        {"intent": "agree", "target": a, "dialogue": "Aye, answer him."}]
    r = gm.npc_controller.take_turn(c, "join", t, THEME)
    assert f"{a} already said" in llm.last_prompt and r["dialogue"] == "Aye, answer him."


def test_a_speaker_sees_what_they_said_earlier_today(gm, llm):
    a, b = npcs(gm)[:2]
    gm.state.day = 1
    gm.record_action(b, "defend_self", "None", dialogue="I never said I saw Maeve.")
    llm.json_answers = [{"intent": "defend_self", "dialogue": "As I said, no."}]
    gm.npc_controller.take_turn(b, "answer", thread_with((a, "question", b, "Did you see Maeve?")), THEME)
    assert ('WHAT YOU SAID EARLIER TODAY (stay consistent with it, or say why you changed your mind):\n'
            '- "I never said I saw Maeve."') in llm.last_prompt


def test_the_days_question_after_a_killing_and_after_a_quiet_night(gm):
    from models.clues import Clue
    gm.state.day = 2
    gm.state.killed_last_night = ["Silas"]
    gm.state.clues.add(Clue(2, "Silas", "the mill race", "wax", "herring"))
    theme = gm.get_day_theme(["Bram (who claims to be the Coroner): Maeve was no wolf."])
    assert theme.startswith("Who killed Silas last night? Silas was found at the mill race, with traces of wax")
    assert theme.endswith("This morning's reports: Bram (who claims to be the Coroner): Maeve was no wolf.")
    gm.state.killed_last_night = []
    assert gm.get_day_theme().startswith("Nobody died last night.")


# --- the discussion phase ----------------------------------------------------------------

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
        if "opens today's discussion" in user_prompt or "moves the discussion forward" in user_prompt:
            n = sum(1 for c in self.calls if "moves the discussion forward" in c[2] or "opens today's" in c[2])
            return {"intent": "question", "target": other, "dialogue": f"{other}, where were you? ({n})",
                    "angle": f"where {other} was"}
        if "just said to you" in user_prompt:
            return {"intent": "defend_self", "dialogue": f"{speaker} was at home."}
        if "may respond to what was JUST SAID" in user_prompt:
            return self.join(speaker, user_prompt)
        return {}


def run_day(gm, llm, **cfg):
    gm.llm = llm
    gm.state.day = 1
    gm.state.roles_known = True
    gm.config.update(cfg)
    gm.stat_engine.check_all_reveals = lambda: []
    DiscussionPhase(gm).run()
    return gm.state.threads[1][0]


def test_the_day_is_one_conversation_and_questions_are_answered_next(gm, io):
    t = run_day(gm, ScriptedLLM(npcs(gm)), turns_per_day=4)
    assert len(gm.state.threads[1]) == 1
    asked = t.turns[0].target
    assert t.turns[1].speaker == asked and t.turns[1].dialogue == f"{asked} was at home."
    assert gm.state.phase == GamePhase.VOTING


def test_the_day_ends_when_its_lines_run_out(gm, io):
    t = run_day(gm, ScriptedLLM(npcs(gm)), turns_per_day=5)
    assert 5 <= len(t.turns) <= 6  # a last question may still get its answer


def test_every_line_reaches_the_chat_history_in_order(gm, io):
    t = run_day(gm, ScriptedLLM(npcs(gm)), turns_per_day=4)
    lines = [l for l in gm.state.chat_history if not l.startswith("[Town Crier")]
    assert lines == [turn.line() for turn in t.turns]


def test_the_players_question_is_answered_next(gm, io):
    names = npcs(gm)
    llm = ScriptedLLM(names)
    io.inputs = ["", "PLAYER_Q"]  # let the opening line through, then speak
    picked = {}
    original = gm.player_controller.process_reaction

    def process_reaction(text, *a, **k):
        first = gm.state.threads[1][0].turns[0]
        picked["t"] = next(n for n in names if n not in (first.speaker, first.target))
        llm.player_parse = {"intent": "question", "target": picked["t"], "summary": "asked"}
        return original(text, *a, **k)

    gm.player_controller.process_reaction = process_reaction
    t = run_day(gm, llm, turns_per_day=6)
    i = next(i for i, turn in enumerate(t.turns) if turn.speaker == "Player")
    assert t.turns[i].target == picked["t"] and t.turns[i + 1].speaker == picked["t"]


def test_a_role_claim_is_spoken_into_the_conversation(gm, io):
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
    for fn in ("register_reveal", "apply_reveal_pressure", "process_duplicate_claim"):
        setattr(gm.stat_engine, fn, lambda *a: None)
    gm.llm = llm
    gm.state.day = 1
    gm.state.roles_known = True
    gm.config.update(turns_per_day=3)
    gm.stat_engine.check_all_reveals = reveals
    DiscussionPhase(gm).run()
    t = gm.state.threads[1][0]
    assert t.turns[0].speaker == claimant and t.turns[0].intent == "reveal_role"
    assert len(t.turns) > 1  # the conversation goes on after the claim


def test_a_silent_player_is_noticed_when_pressed(gm, io):
    names = npcs(gm)

    class AccusePlayer(ScriptedLLM):
        def generate_json(self, system_prompt, user_prompt, *a, **k):
            if "opens today's discussion" in user_prompt:
                self.calls.append(("json", system_prompt, user_prompt))
                return {"intent": "accuse", "target": "Player", "dialogue": "The stranger did it."}
            return super().generate_json(system_prompt, user_prompt, *a, **k)

    run_day(gm, AccusePlayer(names), turns_per_day=3)
    assert "You refused to defend yourself" in "\n".join(io.lines)
    assert any(r["intent"] == "silent" for r in gm.state.public_record)


def test_a_lead_with_nothing_to_say_hands_the_floor_on(gm, io):
    names = npcs(gm)
    first = {}

    class Mute(ScriptedLLM):
        def generate_json(self, system_prompt, user_prompt, *a, **k):
            speaker = re.match(r"You are (\w+)", system_prompt).group(1)
            if "opens today's discussion" in user_prompt and not first:
                first["who"] = speaker
                self.calls.append(("json", system_prompt, user_prompt))
                return {"intent": "neutral", "dialogue": ""}
            return super().generate_json(system_prompt, user_prompt, *a, **k)

    t = run_day(gm, Mute(names), turns_per_day=2)
    assert t.turns[0].speaker != first["who"]
    assert "Glares" not in "\n".join(io.lines)


def test_show_threads_shows_the_question_and_each_angle(gm, io):
    gm.debug["show_threads"] = True
    run_day(gm, ScriptedLLM(npcs(gm)), turns_per_day=3)
    out = "\n".join(io.lines)
    assert "— today: Nobody died last night." in out and "— angle 1: where" in out
