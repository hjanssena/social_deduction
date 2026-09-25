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
    line, _ = gm.conversation_controller.reply(wolf, ["[Player (the traveler)]: Are you a wolf?"], private=True)
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
    gm.npc_controller.take_turn(other, "lead", None, "Who killed Silas?")
    assert "SWORDFISH" not in llm.last_prompt


def test_chat_menu_is_drawn_once_per_day(gm, llm, io):
    gm.state.day = 2
    io.inputs = ["6"]  # 5 villagers on offer, option 6 is "Nobody"
    ChatsPhase(gm).run()
    first = list(gm.state.chat_options[2])
    ChatsPhase(gm).run()
    assert gm.state.chat_options[2] == first and len(first) == 5


def test_evening_chat_remembers_todays_vote(gm, llm):
    state = gm.state
    elara, silas = npcs(gm)[:2]
    state.day = 1
    state.votes_by_day[1] = {"Player": silas, elara: "Player", silas: "Player"}
    state.public_events.append(f"Day 1 votes: Player -> {silas}, {elara} -> Player, {silas} -> Player.")
    state.last_verdict = {"day": 1, "hanged": silas, "text": f"The town hanged {silas}.", "drew_votes": []}
    llm.text_answers = ["Yes, I voted for you."]
    gm.conversation_controller.reply(elara, [], private=True)
    assert "At today's vote you voted to hang the traveler" in llm.last_prompt
    assert f"Today: The town hanged {silas}." in llm.last_prompt
    assert f"{elara} -> Player" in llm.last_prompt


def test_public_claimant_may_speak_of_their_claim_in_private(gm, llm):
    learn_roles(gm)
    coroner = next((n for n, r in gm.state.roles.items() if r == "coroner" and n != "Player"), None)
    if not coroner:
        return
    gm.state.revealed_roles[coroner] = "coroner"
    llm.text_answers = ["I am the Coroner, and I stand by what I found."]
    line, _ = gm.conversation_controller.reply(coroner, [], private=True)
    assert line.startswith("I am the Coroner")
    assert "already claimed to be the Coroner" in llm.last_prompt
    assert "ROLE CLAIMS MADE IN PUBLIC" in llm.last_prompt


def test_villager_can_close_a_private_chat_early(gm, io, llm):
    name = npcs(gm)[0]
    llm.text_answers = ["Evening.", "Enough talk for one night. [END]"]
    io.inputs = ["Hello there.", "One more thing...", "And another."]
    run_private_chat(gm, name)
    said = [t for t in gm.state.private_chats[-1]["transcript"] if t.startswith("[Player")]
    assert len(said) == 1  # the villager ended it after the first reply
    assert "[END]" not in "\n".join(gm.state.private_chats[-1]["transcript"])


def test_last_reply_closes_without_a_question(gm, llm):
    name = npcs(gm)[0]
    llm.text_answers = ["Safe travels."]
    line, ended = gm.conversation_controller.reply(name, [], private=True, last=True)
    assert ended and line == "Safe travels."
    assert "Do not ask them anything" in llm.last_prompt


def test_a_closing_reply_that_asks_something_keeps_the_chat_open(gm, llm):
    llm.text_answers = ["Sleep well. But what brings you here? [END]"]
    line, ended = gm.conversation_controller.reply(npcs(gm)[0], [], private=True)
    assert not ended and "[END]" not in line


def test_clean_strips_a_speaker_label_but_not_speech():
    from core.controllers.conversation_controller import ConversationController
    clean = ConversationController._clean
    assert clean("Sol Badguy", "[Sol Badguy -> Player]: Tch.") == "Tch."
    assert clean("Sol Badguy", "Sol Badguy: Tch.") == "Tch."
    said = "Sol Badguy. Bounty hunter. You're either: running or hunting."
    assert clean("Sol Badguy", said) == said
