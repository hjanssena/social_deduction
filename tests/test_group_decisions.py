"""Grouped votes and night actions: one call per side, validated, engine fallback."""


def sides(gm):
    wolves = [n for n in gm.state.alive_characters if gm.state.roles.get(n) == "werewolf"]
    village = [n for n in gm.state.alive_characters if n not in wolves]
    return wolves, village


def npc(names):
    return [n for n in names if n != "Player"]


def test_village_votes_are_taken_and_bad_ones_fall_back(gm, llm):
    wolves, village = sides(gm)
    voters = npc(village)
    a, b = voters[0], voters[1]
    llm.json_answers = [
        {"votes": [{"voter": a, "reasoning": "r", "vote": b},
                   {"voter": b, "reasoning": "r", "vote": b}]},   # self vote: retried
        {"votes": [{"voter": b, "reasoning": "r2", "vote": a}]},
    ]
    res = gm.npc_controller.decide_votes(voters)
    assert res[a]["target"] == b
    assert res[b] == {"target": a, "thought_process": "r2"}
    assert set(res) == set(voters)  # everyone else filled in by the engine


def test_village_prompt_never_names_the_pack(gm, llm):
    wolves, village = sides(gm)
    gm.npc_controller.decide_votes(npc(village))
    village_prompt = llm.calls[0][2]
    assert "fellow werewolves" not in village_prompt
    assert "werewolf pack" not in village_prompt


def test_wolves_never_vote_for_packmates(gm, llm):
    wolves, village = sides(gm)
    w = npc(wolves)
    if len(w) < 2:
        return
    llm.json_answers = [{"votes": [{"voter": w[0], "vote": w[1]}]},
                        {"votes": [{"voter": w[0], "vote": w[1]}]}]
    res = gm.npc_controller.decide_votes([w[0]])
    assert res[w[0]]["target"] not in wolves


def test_dict_shaped_votes_are_accepted(gm, llm):
    wolves, village = sides(gm)
    a, b = npc(village)[:2]
    llm.json_answers = [{"votes": {a: {"vote": b, "reasoning": "r"}, b: a}}]
    res = gm.npc_controller.decide_votes([a, b])
    assert (res[a]["target"], res[b]["target"]) == (b, a)


def test_kill_decision_and_whispers(gm, llm):
    wolves, village = sides(gm)
    w = npc(wolves)[0]
    victim = npc(village)[0]
    llm.json_answers = [{"whispers": [{"wolf": w, "preference": victim, "whisper": "Tonight."}],
                         "reasoning": "x", "target": victim.lower()}]
    d = gm.npc_controller.decide_kill(wolves, village)
    assert d["target"] == victim and d["whispers"] == {w: "Tonight."}


def test_invalid_kill_target_falls_back(gm, llm):
    wolves, village = sides(gm)
    llm.json_answers = [{"target": wolves[0]}]
    assert gm.npc_controller.decide_kill(wolves, village)["target"] in village


def test_protection_outside_choices_falls_back(gm, llm):
    names = npc(gm.state.alive_characters)
    ga, excluded = names[0], names[1]
    choices = [n for n in gm.state.alive_characters if n not in (ga, excluded)]
    llm.json_answers = [{"target": excluded}]
    assert gm.npc_controller.decide_protection(ga, choices)["target"] in choices
    assert f"cannot protect {excluded} again" in llm.last_prompt
