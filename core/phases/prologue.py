import random
from core.game_state import GamePhase


class ProloguePhase:
    """Day 0 introduction. Pre-fills the chat window to prime the AI."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state

        io.show_phase("THE GATHERING", state.day)

        io.show_narration("The wind howls against the thick wooden shutters of the local tavern.")
        io.show_narration("In a settlement this small, a sudden gathering called by the Mayor is never a good sign.")
        io.show_narration("The handful of residents murmur nervously, their faces illuminated by the flickering hearth.")
        io.show_narration("Victor stands at the head of the room, looking older and more tired than anyone has ever seen him.")
        io.show_narration("He raises a heavy hand, and the tavern falls dead silent.")

        io.pause()

        # Victor's opening
        opening_statement = (
            "Friends, please... I have terrible news. My uncle has vanished in the night. "
            "His room was left in a struggle. I fear foul play, and I fear the culprit is in this very room."
        )

        state.chat_history.append(f"[Victor -> Room]: {opening_statement}")
        io.show_dialogue("Victor", "Room", opening_statement)

        state.logical_history.append("Victor [accuse] -> Room (Emotion: fearful). Reason: His uncle is missing.")

        fallback_reactions = [
            "This is madness. Who would do such a thing?",
            "I can't believe this is happening... right under our noses.",
            "We need to figure out who is responsible, quickly, before they strike again."
        ]

        # Pick other characters to react
        available_npcs = [name for name in state.alive_characters if name not in ["Victor", "Player"]]
        random.shuffle(available_npcs)
        reactors = available_npcs[:3]

        for npc in reactors:
            char_obj = gm.characters.get(npc)

            if char_obj and char_obj.prologue_reactions:
                reaction = random.choice(char_obj.prologue_reactions)
            else:
                reaction = random.choice(fallback_reactions)

            state.chat_history.append(f"[{npc} -> Room]: {reaction}")
            io.show_dialogue(npc, "Room", reaction)

            state.logical_history.append(
                f"{npc} [neutral] -> Room (Emotion: suspicious). Reason: Reacting to the Mayor's news."
            )
            io.pause()

        io.show_system("The shock settles. The room turns to each other in suspicion...", style="muted")
        io.pause()

        self._reveal_role(state, io)

        io.pause()
        state.phase = GamePhase.DISCUSSION

    def _reveal_role(self, state, io):
        player_role = state.roles.get("Player", "villager")

        if player_role == "werewolf":
            pack = [name for name, role in state.roles.items() if role == "werewolf" and name != "Player"]
            lines = ["You are a WEREWOLF."]
            if pack:
                lines.append(f"Your fellow pack members are: {', '.join(pack)}")
                lines.append("Do not attack them. Protect them if they fall under suspicion.")
            else:
                lines.append("You are the lone werewolf. Trust no one.")
            lines.append("Goal: Deceive the town, survive the voting phase, and eliminate them all.")
        elif player_role == "guardian_angel":
            lines = [
                "You are the GUARDIAN ANGEL.",
                "Each night, you may protect one person from the werewolf attack.",
                "You cannot protect yourself. You cannot protect the same person two nights in a row.",
                "Goal: Keep the innocent alive and help the town find the werewolves.",
            ]
        elif player_role == "coroner":
            lines = [
                "You are the CORONER.",
                "After each lynch, you privately learn the true role of the executed person.",
                "The town will NOT see public role reveals while you are alive.",
                "Goal: Use your knowledge wisely during discussion to guide the town.",
            ]
        else:
            lines = [
                "You are an INNOCENT VILLAGER.",
                "Goal: Find the werewolves, convince the town, and vote to lynch them before it's too late.",
            ]

        io.show_role_reveal_private(player_role, lines)
