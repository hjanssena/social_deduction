from core.game_state import GamePhase


class ArrivalPhase:
    """Day 0: the traveler reaches the village. Nobody knows their role yet."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state

        io.show_phase("THE ARRIVAL", state.day)

        io.show_system("The townsfolk gather their thoughts...", style="muted")
        for name in state.logbooks:
            gm.npc_controller.write_opening_entry(name)

        io.show_narration("Night is falling when you reach the village, a handful of crooked roofs hemmed in by pines.")
        io.show_narration("The tavern is the only building with light in its windows, so that is where you go.")
        io.show_narration("Inside, the villagers go quiet and turn to look at the stranger in the doorway.")
        io.pause()

        for name in state.logbooks:
            io.show_narration(f"{name}, the {gm.characters[name].occupation.lower()}, watches you from across the room.")
        io.pause()

        io.show_narration("You take a room upstairs. Somewhere in the woods, something howls.")
        io.pause()
        state.phase = GamePhase.NIGHT
