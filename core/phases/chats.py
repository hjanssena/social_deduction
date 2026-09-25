import random

from core.controllers.conversation_controller import TRAVELER
from core.game_state import GamePhase


def run_private_chat(gm, name: str, max_comments: int = 3):
    """A private talk between the traveler and one villager: the villager opens, the player may
    speak up to `max_comments` times, and the villager logs the conversation in the background."""
    io = gm.io
    conv = gm.conversation_controller
    io.show_narration(f"You find {name} alone, away from the others.")

    transcript = []
    line = conv.open_chat(name)
    io.show_dialogue(name, "Player", line)
    transcript.append(f"[{name}]: {line}")
    for i in range(max_comments):
        said = io.prompt_say(name, remaining=max_comments - i)
        if not said.strip():
            break
        transcript.append(f"[{TRAVELER}]: {said}")
        line = conv.reply(name, transcript, private=True)
        io.show_dialogue(name, "Player", line)
        transcript.append(f"[{name}]: {line}")

    gm.state.private_chats.append({"day": gm.state.day, "with": name, "transcript": transcript})
    gm.background.submit(gm.npc_controller.write_entry, name, "Private talk with the traveler",
                         ["You spoke with the traveler (Player) in private. Nobody else heard it:"] + transcript)


class ChatsPhase:
    """Evening: five villagers are around (drawn once per day); the player may talk privately to two."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state
        io.show_phase("EVENING", state.day)

        npcs = [n for n in state.alive_characters if n != "Player"]
        if state.day not in state.chat_options:
            state.chat_options[state.day] = random.sample(npcs, min(5, len(npcs)))
        options = [n for n in state.chat_options[state.day] if n in state.alive_characters]

        chosen = []
        for i in range(min(2, len(options))):
            available = [o for o in options if o not in chosen]
            menu = available + ["Nobody, I'll turn in for the night"]
            choice = io.prompt_menu(f"Who do you want to talk to this evening? ({i + 1} of 2)", menu, context="chat")
            if choice >= len(available):
                break
            chosen.append(available[choice])
            run_private_chat(gm, available[choice])

        state.phase = GamePhase.NIGHT
