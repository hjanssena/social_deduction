"""Introductions and private chats: silence remarks, leak checks, privacy, the daily chat menu."""
from core.game_state import GamePhase
from core.phases import ArrivalPhase, ChatsPhase
from core.phases.chats import run_private_chat


def npcs(gm):
    return [n for n in gm.state.alive_characters if n != "Player"]


def learn_roles(gm):
    gm.state.roles_known = True
    wolves = [n for n, r in gm.state.roles.items() if r == "werewolf"]
    for book in gm.state.logbooks.values():
        if gm.state.roles.get(book.owner) == "werewolf":
            book.assign_pack(wolves)
    return wolves


def test_leak_detector(gm):
    conv = gm.conversation_controller
    wolves = learn_roles(gm)
    wolf = next(w for w in wolves if w != "Player")
    villager = next(n for n in npcs(gm) if gm.state.roles[n] == "villager")
    mate = next(w for w in wolves if w != wolf)
    assert conv.leaks_secret(wolf, "Between us, I am a werewolf.")
    assert conv.leaks_secret(wolf, "My pack will feed tonight.")
    assert conv.leaks_secret(wolf, f"{mate} and I hunt together, we wolves are patient.") or mate == "Player"
    assert conv.leaks_secret(villager, "Fine. I'm the Coroner, and I know things.")
    assert not conv.leaks_secret(villager, "As the Coroner told us, Victor was innocent.")
    assert not conv.leaks_secret(villager, "The wolves will strike again tonight.")


def test_no_leaks_before_roles_are_known(gm):
    wolf = next(n for n, r in gm.state.roles.items() if r == "werewolf" and n != "Player")
    assert not gm.conversation_controller.leaks_secret(wolf, "I am a werewolf.")


def test_wolf_can_speak_freely_to_a_packmate_player(gm):
    gm.state.roles["Player"] = "werewolf"
    wolves = learn_roles(gm)
    wolf = next(w for w in wolves if w != "Player")
    assert not gm.conversation_controller.leaks_secret(wolf, "We are wolves, you and I.", listener="Player")


def test_leaking_line_is_retried_then_deflected(gm, llm):
    wolves = learn_roles(gm)
    wolf = next(w for w in wolves if w != "Player")
    llm.text_answers = ["I am a werewolf.", "Fine, I'm a wolf."]
    line = gm.conversation_controller.reply(wolf, ["[Player (the traveler)]: Are you a wolf?"], private=True)
    assert "werewolf" not in line.lower() and "wolf" not in line.lower().split()
    assert "You almost said" in llm.calls[1][2]


def test_silent_traveler_draws_remarks_and_arrival_has_no_roles(gm, llm, io):
    llm.text_answers = [f"line {i}" for i in range(40)]
    ArrivalPhase(gm).run()  # The player presses Enter everywhere, then picks the first chat option
    prompts = [c[2] for c in llm.calls]
    remarks = [p for p in prompts if "said nothing at all" in p]
    assert len(remarks) >= 4  # ceil(7 / 2) introductions, each met with silence
    assert all("SECRET ROLE" not in c[1] for c in llm.calls)
    assert gm.state.phase == GamePhase.NIGHT
    assert len(gm.state.private_chats) == 1


def test_private_chat_stays_private(gm, llm, io):
    learn_roles(gm)
    name, other = npcs(gm)[:2]
    io.inputs = ["The password is SWORDFISH.", ""]
    llm.text_answers = ["Evening.", "Interesting."]
    run_private_chat(gm, name)
    assert "SWORDFISH" in gm.state.private_chats[-1]["transcript"][1]
    assert "SWORDFISH" not in gm.get_public_record_text()
    llm.json_answers = [{"intent": "neutral", "dialogue": "hm"}]
    gm.npc_controller.generate_assertion(other, 0)
    assert "SWORDFISH" not in llm.last_prompt


def test_chat_menu_is_drawn_once_per_day(gm, llm, io):
    gm.state.day = 2
    io.inputs = ["6"]  # 5 villagers on offer, option 6 is "Nobody"
    ChatsPhase(gm).run()
    first = list(gm.state.chat_options[2])
    ChatsPhase(gm).run()
    assert gm.state.chat_options[2] == first and len(first) == 5
