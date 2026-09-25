"""Assertion / reaction decisions: the LLM decides, the controller validates."""
from core.phases.discussion import DiscussionPhase


def npc_names(gm):
    return [n for n in gm.state.alive_characters if n != "Player"]


def test_valid_decision_passes_through(gm, llm):
    speaker, other = npc_names(gm)[:2]
    llm.json_answers = [{"intent": "Accuse", "target": other.lower(), "emotion": "Angry",
                         "dialogue": f"{other} lies!", "thought": "t"}]
    r = gm.npc_controller.generate_assertion(speaker, 0)
    assert (r["intent"], r["target"], r["emotion"]) == ("accuse", other, "angry")


def test_defending_yourself_becomes_defend_self(gm, llm):
    speaker = npc_names(gm)[0]
    llm.json_answers = [{"intent": "defend", "target": speaker, "dialogue": "I did nothing"}]
    r = gm.npc_controller.generate_assertion(speaker, 0)
    assert (r["intent"], r["target"]) == ("defend_self", "None")


def test_missing_target_recovered_from_dialogue(gm, llm):
    speaker, other = npc_names(gm)[:2]
    llm.json_answers = [{"intent": "accuse", "target": "None", "dialogue": f"{other}, you lie."}]
    r = gm.npc_controller.generate_assertion(speaker, 0)
    assert (r["intent"], r["target"]) == ("accuse", other)


def test_unknown_intent_and_emotion_fall_back_to_neutral(gm, llm):
    speaker = npc_names(gm)[0]
    llm.json_answers = [{"intent": "dance", "target": "Nobody", "dialogue": "hi", "emotion": "giddy"}]
    r = gm.npc_controller.generate_assertion(speaker, 0)
    assert (r["intent"], r["target"], r["emotion"]) == ("neutral", "None", "neutral")


def test_empty_answer_glares(gm, llm):
    r = gm.npc_controller.generate_assertion(npc_names(gm)[0], 0)
    assert r["dialogue"] == "... (Glares in silence)"


def test_silent_reaction_returns_none(gm, llm):
    speaker, reactor = npc_names(gm)[:2]
    llm.json_answers = [{"intent": "silent", "dialogue": ""}]
    assert gm.npc_controller.process_reaction(speaker, {"intent": "accuse", "target": reactor, "dialogue": "x"},
                                              reactor, 0) is None


def test_agree_without_target_agrees_with_speaker(gm, llm):
    speaker, reactor = npc_names(gm)[:2]
    llm.json_answers = [{"intent": "agree", "target": "None", "dialogue": "Aye."}]
    r = gm.npc_controller.process_reaction(speaker, {"intent": "neutral", "target": "None", "dialogue": "x"},
                                           reactor, 0)
    assert (r["intent"], r["target"]) == ("agree", speaker)


def test_repeat_guard_retries_once(gm, llm):
    speaker = npc_names(gm)[0]
    gm.record_action(speaker, "neutral", dialogue="Easy there, friend.")
    llm.json_answers = [{"intent": "neutral", "dialogue": "Easy there, friend!"},
                        {"intent": "neutral", "dialogue": "Pour another."}]
    r = gm.npc_controller.generate_assertion(speaker, 0)
    assert r["dialogue"] == "Pour another."
    assert "You already said" in llm.last_prompt


def test_reaction_queue_puts_target_and_friends_first(gm):
    names = npc_names(gm)
    speaker = names[0]
    # Pick a target who has at least one friend among the others
    target = next(t for t in names[1:] if any(gm.state.logbooks[n].relation_to(t) == "friend"
                                               for n in names if n not in (t, speaker)))
    queue = gm.npc_controller.build_reaction_queue(speaker, target)
    assert queue[0] == target
    assert gm.state.logbooks[queue[1]].relation_to(target) == "friend" or target in gm.state.logbooks[queue[1]].pack
    assert len(queue) <= gm.config.get("max_reactions_per_assertion", 3)


def test_commit_records_public_action(gm):
    speaker, target = npc_names(gm)[:2]
    DiscussionPhase(gm)._commit_assertion(speaker, {"intent": "accuse", "target": target, "emotion": "angry",
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
    assert gm.npc_controller.generate_assertion(speaker, 0)["dialogue"] == "Fresh words."
