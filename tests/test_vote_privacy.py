"""Vote reveals show only what a voter says aloud, never their private reasoning."""
import re

from core.phases import VotingPhase


def plain(io):
    return re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(io.lines))


def wolf_npcs(gm):
    return [n for n, r in gm.state.roles.items() if r == "werewolf" and n != "Player"]


def learn_roles(gm):
    gm.state.roles_known = True
    wolves = [n for n, r in gm.state.roles.items() if r == "werewolf"]
    for name in wolves:
        if name in gm.state.logbooks:
            gm.state.logbooks[name].assign_pack(wolves)


def reveal(gm, voter, result):
    all_votes = {}
    VotingPhase(gm)._reveal_npc_votes([voter], {voter: result}, all_votes)
    return all_votes


def test_private_reasoning_is_hidden_without_debug(gm, io, monkeypatch):
    monkeypatch.setattr("core.phases.voting.REVEAL_PAUSE_SECONDS", 0)
    learn_roles(gm)
    wolf = wolf_npcs(gm)[0]
    target = next(n for n in gm.state.alive_characters if gm.state.roles[n] != "werewolf")
    reveal(gm, wolf, {"target": target, "thought_process": "Hanging them keeps my pack safe.",
                      "says": "They dodged every question today."})
    out = plain(io)
    assert "keeps my pack safe" not in out
    assert "They dodged every question today." in out and f"My vote is for {target}." in out


def test_reasoning_shows_in_debug_mode(gm, io, monkeypatch):
    monkeypatch.setattr("core.phases.voting.REVEAL_PAUSE_SECONDS", 0)
    gm.debug["show_logic"] = True
    learn_roles(gm)
    wolf = wolf_npcs(gm)[0]
    target = next(n for n in gm.state.alive_characters if gm.state.roles[n] != "werewolf")
    reveal(gm, wolf, {"target": target, "thought_process": "Keeps my pack safe.", "says": "Hm."})
    assert "Keeps my pack safe." in plain(io)


def test_leaky_public_line_is_dropped(gm, io, monkeypatch):
    monkeypatch.setattr("core.phases.voting.REVEAL_PAUSE_SECONDS", 0)
    learn_roles(gm)
    wolf = wolf_npcs(gm)[0]
    target = next(n for n in gm.state.alive_characters if gm.state.roles[n] != "werewolf")
    reveal(gm, wolf, {"target": target, "thought_process": "x", "says": "My pack needs this one gone."})
    out = plain(io)
    assert "My pack" not in out and f"My vote is for {target}." in out


def test_hanged_wolf_never_confesses_in_final_words(gm, llm):
    learn_roles(gm)
    wolf = wolf_npcs(gm)[0]
    llm.text_answers = ["Fine! I am a werewolf, and I regret nothing.", "Yes, we wolves will feast."]
    words = gm.npc_controller.generate_final_words(wolf)
    assert "werewolf" not in words.lower() and "wolves" not in words.lower()


def test_real_role_holder_may_claim_in_final_words(gm, llm):
    learn_roles(gm)
    coroner = next((n for n, r in gm.state.roles.items() if r == "coroner" and n != "Player"), None)
    if coroner:
        llm.text_answers = ["I am the Coroner, and you have hanged the wrong person."]
        assert gm.npc_controller.generate_final_words(coroner).startswith("I am the Coroner")
