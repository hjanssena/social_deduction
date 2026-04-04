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

        io.display("\n" + "="*50)
        io.display("                 THE GATHERING")
        io.display("="*50 + "\n")

        io.display("\033[36mThe wind howls against the thick wooden shutters of the local tavern.\033[0m")
        io.display("\033[36mIn a settlement this small, a sudden gathering called by the Mayor is never a good sign.\033[0m")
        io.display("\033[36mThe handful of residents murmur nervously, their faces illuminated by the flickering hearth.\033[0m")
        io.display("\033[36mVictor stands at the head of the room, looking older and more tired than anyone has ever seen him.\033[0m")
        io.display("\033[36mHe raises a heavy hand, and the tavern falls dead silent.\033[0m\n")

        io.pause()
        io.display("")

        # Victor's opening
        opening_statement = (
            "Friends, please... I have terrible news. My uncle has vanished in the night. "
            "His room was left in a struggle. I fear foul play, and I fear the culprit is in this very room."
        )

        state.chat_history.append(f"[Victor -> Room]: {opening_statement}")
        io.display(f"[Victor -> Room]: {opening_statement}")

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
            io.display(f"[{npc} -> Room]: {reaction}")

            state.logical_history.append(
                f"{npc} [neutral] -> Room (Emotion: suspicious). Reason: Reacting to the Mayor's news."
            )
            io.pause()

        io.display("\n\033[90m[System]: The shock settles. The room turns to each other in suspicion...\033[0m")
        io.pause()

        self._reveal_role(state, io)

        io.pause("\033[90m[Press Enter to begin Discussion] >\033[0m ")
        state.phase = GamePhase.DISCUSSION

    def _reveal_role(self, state, io):
        player_role = state.roles.get("Player", "villager")
        io.display("\n" + "="*50)
        io.display("                 YOUR SECRET ROLE")
        io.display("="*50)

        if player_role == "werewolf":
            io.display("\033[91mYou are a WEREWOLF.\033[0m")
            pack = [name for name, role in state.roles.items() if role == "werewolf" and name != "Player"]
            if pack:
                io.display(f"\033[91mYour fellow pack members are: {', '.join(pack)}\033[0m")
                io.display("\033[91mDo not attack them. Protect them if they fall under suspicion.\033[0m")
            else:
                io.display("\033[91mYou are the lone werewolf. Trust no one.\033[0m")
            io.display("\033[91mGoal: Deceive the town, survive the voting phase, and eliminate them all.\033[0m")
        else:
            io.display("\033[92mYou are an INNOCENT VILLAGER.\033[0m")
            io.display("\033[92mGoal: Find the werewolves, convince the town, and vote to lynch them before it's too late.\033[0m")
