"""Discussion turns: the LLM decides, the controller validates."""
from core.phases.discussion import DiscussionPhase
from models.thread import Thread, Turn


def thread(speaker, intent, target, dialogue):
    t = Thread(day=1, opener=speaker)
    t.add(Turn(speaker, intent, target, dialogue))
    return t


def npc_names(gm):
    return [n for n in gm.state.alive_characters if n != "Player"]


def test_valid_decision_passes_through(gm, llm):
    speaker, other = npc_names(gm)[:2]
    llm.json_answers = [{"intent": "Accuse", "target": other.lower(), "emotion": "Angry",
                         "dialogue": f"{other} lies!", "thought": "t"}]
    r = gm.npc_controller.take_turn(speaker, "lead", None, "Who killed Silas?")
    assert (r["intent"], r["target"], r["emotion"]) == ("accuse", other, "angry")


def test_defending_yourself_becomes_defend_self(gm, llm):
    speaker = npc_names(gm)[0]
    llm.json_answers = [{"intent": "defend", "target": speaker, "dialogue": "I did nothing"}]
    r = gm.npc_controller.take_turn(speaker, "lead", None, "Who killed Silas?")
    assert (r["intent"], r["target"]) == ("defend_self", "None")


def test_missing_target_recovered_from_dialogue(gm, llm):
    speaker, other = npc_names(gm)[:2]
    llm.json_answers = [{"intent": "accuse", "target": "None", "dialogue": f"{other}, you lie."}]
    r = gm.npc_controller.take_turn(speaker, "lead", None, "Who killed Silas?")
    assert (r["intent"], r["target"]) == ("accuse", other)


def test_unknown_intent_and_emotion_fall_back_to_neutral(gm, llm):
    speaker = npc_names(gm)[0]
    llm.json_answers = [{"intent": "dance", "target": "Nobody", "dialogue": "hi", "emotion": "giddy"}]
    r = gm.npc_controller.take_turn(speaker, "lead", None, "Who killed Silas?")
    assert (r["intent"], r["target"], r["emotion"]) == ("neutral", "None", "neutral")


def test_empty_opening_leaves_the_floor(gm, llm):
    assert gm.npc_controller.take_turn(npc_names(gm)[0], "lead", None, "Who killed Silas?") is None


def test_passing_joiner_returns_none(gm, llm):
    speaker, reactor = npc_names(gm)[:2]
    llm.json_answers = [{"intent": "silent", "dialogue": ""}]
    assert gm.npc_controller.take_turn(reactor, "join", thread(speaker, "accuse", reactor, "x"), "Who killed Silas?") is None


def test_answer_agreeing_without_target_agrees_with_the_asker(gm, llm):
    speaker, reactor = npc_names(gm)[:2]
    llm.json_answers = [{"intent": "agree", "target": "None", "dialogue": "Aye."}]
    r = gm.npc_controller.take_turn(reactor, "answer", thread(speaker, "question", reactor, "Right?"), "Who killed Silas?")
    assert (r["intent"], r["target"]) == ("agree", speaker)


def test_repeat_guard_retries_once(gm, llm):
    speaker = npc_names(gm)[0]
    gm.record_action(speaker, "neutral", dialogue="Easy there, friend.")
    llm.json_answers = [{"intent": "neutral", "dialogue": "Easy there, friend!"},
                        {"intent": "neutral", "dialogue": "Pour another."}]
    r = gm.npc_controller.take_turn(speaker, "lead", None, "Who killed Silas?")
    assert r["dialogue"] == "Pour another."
    assert "You already said" in llm.last_prompt


def test_commit_records_public_action(gm):
    speaker, target = npc_names(gm)[:2]
    DiscussionPhase(gm)._commit_line(speaker, {"intent": "accuse", "target": target, "emotion": "angry",
                                                    "reasoning": "", "dialogue": "Hm."})
    assert f"- {speaker} accused {target}" in gm.get_public_record_text()


def test_sanitize_target_matching(gm):
    names = npc_names(gm)
    assert gm.sanitize_target(names[0].upper()) == names[0]
    assert gm.sanitize_target(f"{names[1]} the fool") == names[1]
    assert gm.sanitize_target("nobody") == "None"


def test_repeat_guard_catches_copied_example_lines(gm, llm):
    speaker = npc_names(gm)[0]
    examples = gm.characters[speaker].speech_examples.get("neutral", {})
    example = next(v for v in examples.values() if "{target}" not in v)
    llm.json_answers = [{"intent": "neutral", "dialogue": example}, {"intent": "neutral", "dialogue": "Fresh words."}]
    assert gm.npc_controller.take_turn(speaker, "lead", None, "Who killed Silas?")["dialogue"] == "Fresh words."
