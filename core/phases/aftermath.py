import random

from core.game_state import GamePhase


class AftermathPhase:
    """After the vote: a few characters react to the hanging, or bicker about the town's indecision."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state
        verdict = state.last_verdict or {"hanged": None, "text": "The town could not agree on anyone."}

        io.show_phase("AFTERMATH", state.day)
        chain = []
        for reactor in self._reactors(verdict):
            result = gm.npc_controller.react_to_verdict(reactor, verdict["text"], chain)
            if result:
                gm.record_action(reactor, result["intent"], result["target"], dialogue=result["dialogue"])
                if gm.debug.get("show_logic"):
                    io.show_engine_debug(reactor, result["intent"], result["target"],
                                         result["emotion"], result["reasoning"])
                io.show_reaction(reactor, result["target"] if result["target"] != "None" else "Room",
                                 result["dialogue"])
                chain.append({"speaker": reactor, "dialogue": result["dialogue"], "intent": result["intent"]})

            p_react = io.prompt_reaction("the verdict")
            if p_react.strip():
                parsed = gm.player_controller.process_reaction(p_react, "Town Crier", verdict["text"], chain)
                chain.append({"speaker": "Player", "dialogue": p_react, "intent": parsed.get("intent", "neutral")})

        if not chain:
            io.show_system("Nobody has anything to say. The villagers drift home in silence.", style="muted")
        io.pause()
        state.phase = GamePhase.CHATS

    def _reactors(self, verdict: dict) -> list[str]:
        """Those with a stake in the hanged person go first (friends, enemies, packmates), then a
        bystander. After a tie, a few random villagers, the people who drew votes first."""
        state = self.gm.state
        npcs = [n for n in state.alive_characters if n != "Player"]
        random.shuffle(npcs)
        cap = self.gm.config.get("max_reactions_per_assertion", 3)
        hanged = verdict.get("hanged")

        if hanged:
            def stake(n):
                book = state.logbooks.get(n)
                return bool(book and (book.relation_to(hanged) or hanged in book.pack))
            concerned = [n for n in npcs if stake(n)]
            others = [n for n in npcs if n not in concerned]
            return (concerned + others[:1])[:cap]

        drew_votes = [n for n in npcs if n in verdict.get("drew_votes", [])]
        others = [n for n in npcs if n not in drew_votes]
        return (drew_votes + others)[:cap]
