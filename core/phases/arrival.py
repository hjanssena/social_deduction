import math
import random

from core.controllers.conversation_controller import TRAVELER
from core.game_state import GamePhase
from core.phases.chats import run_private_chat


class ArrivalPhase:
    """Day 0: the traveler reaches the village. About half the villagers introduce themselves, the
    rest get a mention. Nobody knows their role yet."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state
        conv = gm.conversation_controller

        io.show_phase("THE ARRIVAL", state.day)
        io.show_system("The townsfolk gather their thoughts...", style="muted")
        for name in state.logbooks:
            gm.npc_controller.write_opening_entry(name)

        io.show_narration("Night is falling when you reach the village, a handful of crooked roofs hemmed in by pines.")
        io.show_narration("The tavern is the only building with light in its windows, so that is where you go.")
        io.show_narration("Inside, the villagers go quiet and turn to look at the stranger in the doorway.")
        io.pause()

        villagers = list(state.logbooks)
        random.shuffle(villagers)
        count = math.ceil(len(villagers) / 2)
        introduced, mentioned = villagers[:count], villagers[count:]

        transcript, answers = [], {}
        for name in introduced:
            line = conv.introduce(name, transcript)
            io.show_dialogue(name, "Player", line)
            transcript.append(f"[{name}]: {line}")

            said = io.prompt_say(name).strip()
            answers[name] = said
            if said:
                transcript.append(f"[{TRAVELER}]: {said}")
                gm.record_action("Player", "neutral", name, dialogue=said)
                reply = conv.reply(name, transcript, private=False)
                io.show_dialogue(name, "Player", reply)
                transcript.append(f"[{name}]: {reply}")
            else:
                transcript.append(f"({TRAVELER} says nothing.)")
                for speaker in self._silence_commenters(name):
                    remark = conv.remark_on_silence(speaker, name, transcript)
                    io.show_dialogue(speaker, "Player", remark)
                    transcript.append(f"[{speaker}]: {remark}")
            io.pause()

        for name in mentioned:
            occupation = gm.characters[name].occupation.lower()
            io.show_narration(f"{name}, the {occupation}, watches you from across the room but says nothing.")
        io.pause()

        # Those who met the traveler write about it while the evening goes on
        for name in introduced:
            said = answers[name]
            facts = ["A stranger, the traveler (Player), walked into the tavern tonight.",
                     f'You introduced yourself. The traveler answered: "{said}"' if said
                     else "You introduced yourself, and the traveler said nothing at all in return.",
                     "What was said at the tavern:"] + transcript
            gm.background.submit(gm.npc_controller.write_entry, name, "Arrival", facts)

        menu = introduced + ["Nobody, I'll go straight to bed"]
        choice = io.prompt_menu("Before turning in, who do you want to talk to in private?", menu, context="chat")
        if choice < len(introduced):
            run_private_chat(gm, introduced[choice])

        io.show_narration("You take a room upstairs. Somewhere in the woods, something howls.")
        io.pause()
        state.phase = GamePhase.NIGHT

    def _silence_commenters(self, introduced: str) -> list[str]:
        """The villager who was snubbed, plus one other who cares about them (friend or enemy)."""
        state = self.gm.state
        others = [n for n in state.logbooks if n != introduced
                  and state.logbooks[n].relation_to(introduced)]
        random.shuffle(others)
        return [introduced] + others[:1]
