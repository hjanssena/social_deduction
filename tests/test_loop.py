"""The game loop: hidden roles until night 0, night rules, verdicts, game over, Guardian Angel claims."""
import random

from core.game_state import GamePhase
from core.phases import AftermathPhase, NightPhase, VotingPhase


def npcs(gm):
    return [n for n in gm.state.alive_characters if n != "Player"]


def wolves(gm):
    return [n for n, r in gm.state.roles.items() if r == "werewolf"]


def village(gm):
    return [n for n in gm.state.alive_characters if n not in wolves(gm)]


def test_no_role_or_pack_before_night_zero(gm):
    assert not gm.state.roles_known
    for name in npcs(gm):
        system = gm.npc_controller._system_prompt(name)
        assert "SECRET ROLE" not in system and "werewolf pack" not in system
        assert gm.state.logbooks[name].pack == []


def test_first_night_reveals_roles_and_spares_the_player(gm, llm):
    gm.state.phase = GamePhase.NIGHT
    llm.json_answers = [{"target": "Player"}]  # Not allowed on night 0: the engine picks instead
    NightPhase(gm).run()

    st = gm.state
    assert st.roles_known and st.day == 1 and st.phase == GamePhase.MORNING
    assert "Player" in st.alive_characters and st.killed_last_night and st.killed_last_night[0] != "Player"
    assert st.ga_protection_history == []  # Nobody protects on night 0
    for name, book in st.logbooks.items():
        assert "Tonight I learned" in book.entries[-1]["text"]
        if st.roles[name] == "werewolf":
            assert set(book.pack) == set(wolves(gm)) - {name}
            assert not set(book.pack) & set(book.enemies)
    assert "SECRET ROLE" in gm.npc_controller._system_prompt(npcs(gm)[0])


def test_packmates_stay_pinned_as_allies(gm):
    a = next(n for n in npcs(gm) if gm.state.roles[n] == "werewolf")
    book = gm.state.logbooks[a]
    book.assign_pack(wolves(gm))
    mate = next((w for w in book.pack if w != "Player"), None)
    if mate:
        book.set_allegiances(friends=[], enemies=[mate], valid_names=npcs(gm))
        assert mate in book.pack and mate not in book.enemies


def test_player_killed_at_night_ends_the_game_without_final_words(gm, io):
    gm.state.phase = GamePhase.NIGHT
    gm.state.roles_known = True
    gm.state.day = 2
    night = NightPhase(gm)
    night._resolve_ga_protection = lambda: None
    night._resolve_kill = lambda w, c: "Player"
    night.run()
    assert gm.state.phase == GamePhase.GAME_OVER and gm.state.game_result == "player_killed"
    assert not any("final words" in line.lower() for line in io.lines)
    assert any("The truth, at last" in line for line in io.lines)


def test_tie_goes_to_a_bickering_aftermath(gm, llm, io):
    a, b = village(gm)[:2]
    VotingPhase(gm)._tally_and_execute({a: b, b: a})
    st = gm.state
    assert st.phase == GamePhase.AFTERMATH and st.last_verdict["hanged"] is None
    assert set(st.last_verdict["drew_votes"]) == {a, b}

    reactor = next(n for n in npcs(gm) if n in (a, b))
    llm.json_answers = [{"intent": "disagree", "target": reactor, "dialogue": "Cowards, the lot of you."}] * 3
    AftermathPhase(gm).run()
    assert st.phase == GamePhase.CHATS
    assert "could not agree" in llm.calls[0][2]


def test_hanging_gives_final_words_then_aftermath(gm, llm, io):
    victim = next(n for n in village(gm) if n != "Player")
    voters = {v: victim for v in npcs(gm) if v != victim}
    llm.text_answers = ["I am innocent!"]
    VotingPhase(gm)._tally_and_execute(voters)
    assert victim not in gm.state.alive_characters
    assert gm.state.last_verdict["hanged"] == victim
    assert gm.state.phase in (GamePhase.AFTERMATH, GamePhase.GAME_OVER)


def test_fake_save_claim_names_the_real_target(gm):
    st = gm.state
    st.roles_known, st.day = True, 3
    victim = next(n for n in village(gm) if n != "Player")
    st.attacked_last_night = st.saved_last_night = victim
    findings = gm.stat_engine._fabricate_findings(wolves(gm)[0], "guardian_angel")
    assert findings == [f"Night 2: Protected {victim} (nobody died, so I must have stopped the wolves)"]


def test_guardian_angel_rolls_the_save_claim_once_per_day(gm, monkeypatch):
    st = gm.state
    ga = next((n for n in npcs(gm) if st.roles[n] == "guardian_angel"), None)
    if not ga:
        return
    st.roles_known, st.day = True, 2
    st.saved_last_night = "Player"
    st.ga_protection_history = ["Night 1: Protected Player (nobody died, so I must have stopped the wolves)"]
    monkeypatch.setattr(random, "random", lambda: 0.99)  # First roll fails...
    assert gm.stat_engine._ga_voluntary_reveal(ga) is None
    monkeypatch.setattr(random, "random", lambda: 0.0)   # ...and there is no second chance today
    assert gm.stat_engine._ga_voluntary_reveal(ga) is None or gm.stat_engine._is_under_attack(ga)
    st.day = 3
    assert gm.stat_engine._ga_voluntary_reveal(ga)["claimed_role"] == "guardian_angel"


def test_victory_message_depends_on_the_players_side(gm, io):
    gm.state.roles["Player"] = "werewolf"
    gm.end_game("werewolves_win")
    assert any("[VICTORY]" in line for line in io.lines)


def test_only_one_wolf_counter_claims_a_role(gm, monkeypatch):
    st = gm.state
    st.roles_known, st.day = True, 2
    wolf_npcs = [n for n in npcs(gm) if st.roles[n] == "werewolf"]
    coroner = next((n for n in npcs(gm) if st.roles[n] == "coroner"), None)
    if len(wolf_npcs) < 2 or not coroner:
        return
    for w in wolf_npcs:
        gm.characters[w].performance = 10  # Every wolf is eager to counter-claim
    monkeypatch.setattr(random, "random", lambda: 0.0)
    gm.stat_engine.register_reveal(coroner, "coroner")
    gm.stat_engine.apply_reveal_pressure(coroner, "coroner")
    reveals = gm.stat_engine.check_all_reveals()
    wolf_claims = [n for n, r in reveals if n in wolf_npcs and r["claimed_role"] == "coroner"]
    assert len(wolf_claims) == 1

    # A wolf's own claim never pressures its packmate to counter-claim
    st.reveal_pressure.clear()
    gm.stat_engine.apply_reveal_pressure(wolf_npcs[0], "guardian_angel")
    assert wolf_npcs[1] not in st.reveal_pressure
