from core.game_state import GamePhase


class MorningPhase:
    """Morning: the village wakes to a body (and its crime scene) or to a quiet night."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state

        io.show_phase("MORNING", state.day)

        # Overnight, memories fade: compact every logbook in the background
        if gm.logbook_config.get("compact_after_night", True):
            for name in state.alive_characters:
                if name in state.logbooks:
                    gm.background.submit(gm.npc_controller.compact_logbook, name)

        if state.killed_last_night:
            victim = state.killed_last_night[0]
            io.show_death(victim, "killed")
            state.morning_event = gm.npc_controller.build_crime_scene(victim)
            io.show_narration(state.morning_event)
        else:
            state.morning_event = (
                "Morning comes and, for once, nobody is missing. Either the wolves stayed away, "
                "or something stopped them."
            )
            io.show_system(state.morning_event, style="success")

        io.pause()
        state.phase = GamePhase.DISCUSSION
