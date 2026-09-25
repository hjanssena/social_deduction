import time
from collections import Counter

from core.dialogue_cache import DialoguePrefetcher
from core.game_state import GamePhase
from core.trust_manager import TrustManager

REVEAL_PAUSE_SECONDS = 1.5


class VotingPhase:
    """Collects player and NPC votes, tallies, and executes the lynch."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state

        # NPC votes are decided in the background (one LLM call per side) while the player chooses
        npc_voters = [name for name in state.alive_characters if name != "Player"]
        prefetcher = DialoguePrefetcher()
        prefetcher.submit(gm.npc_controller.decide_votes, npc_voters)

        player_vote = gm.player_controller.get_vote()

        io.show_system("The townsfolk make up their minds...", style="muted")
        npc_vote_results, _ = prefetcher.get()
        prefetcher.shutdown()
        if npc_vote_results is None:
            npc_vote_results = {npc: gm.stat_engine.compute_vote(npc) for npc in npc_voters}

        # Reveal
        io.show_phase("THE VERDICT", state.day)

        all_votes = {"Player": player_vote}
        self._reveal_player_vote(player_vote)
        self._reveal_npc_votes(npc_voters, npc_vote_results, all_votes)

        ballots = ", ".join(f"{v} -> {t}" for v, t in all_votes.items() if t != "None")
        state.public_events.append(f"Day {state.day} votes: {ballots or 'everyone abstained'}.")
        self._tally_and_execute(all_votes)

    def _reveal_player_vote(self, player_vote):
        io = self.gm.io
        state = self.gm.state

        io.show_vote("Player", player_vote)

        if player_vote == "None":
            state.logical_history.append("Player [neutral] -> Room (Emotion: neutral). Reason: Abstained from voting.")
        else:
            state.logical_history.append(
                f"Player [vote_lynch] -> {player_vote} (Emotion: angry). Reason: Cast vote for execution."
            )
            TrustManager.apply_interaction(state, "Player", player_vote, "vote_lynch", self.gm.characters)

    def _reveal_npc_votes(self, npc_voters, npc_vote_results, all_votes):
        gm = self.gm
        io = gm.io
        state = gm.state

        for npc in npc_voters:
            vote_data = npc_vote_results.get(npc, {})
            target = vote_data.get("target", "None")
            thoughts = vote_data.get("thought_process", "...")
            all_votes[npc] = target

            io.show_vote(npc, target, thoughts=thoughts)

            if target == "None":
                state.logical_history.append(
                    f"{npc} [neutral] -> Room (Emotion: fearful). Reason: Abstained from voting."
                )
            else:
                TrustManager.apply_interaction(state, npc, target, "vote_lynch", gm.characters)
                short_reason = (thoughts[:40] + "...") if len(thoughts) > 40 else thoughts
                state.logical_history.append(
                    f"{npc} [vote_lynch] -> {target} (Emotion: angry). Reason: {short_reason}"
                )

            time.sleep(REVEAL_PAUSE_SECONDS)

    def _final_words(self, condemned: str):
        """Gives the condemned character a chance to speak before execution."""
        gm = self.gm
        io = gm.io
        state = gm.state

        if condemned == "Player":
            last_words = io.prompt_final_words()
            if last_words.strip():
                state.chat_history.append(f"[{condemned} -> Room]: {last_words}")
                state.logical_history.append(
                    f"{condemned} [final_words] -> Room (Emotion: desperate). Reason: Last words before execution."
                )
        else:
            last_words = gm.npc_controller.generate_final_words(condemned)
            io.show_final_words(condemned, last_words)
            state.chat_history.append(f"[{condemned} -> Room]: {last_words}")
            state.logical_history.append(
                f"{condemned} [final_words] -> Room (Emotion: desperate). Reason: Last words before execution."
            )

        io.pause()

    def _tally_and_execute(self, all_votes):
        gm = self.gm
        io = gm.io
        state = gm.state

        vote_counts = Counter(t for t in all_votes.values() if t != "None")
        drew_votes = list(vote_counts)
        for char, count in vote_counts.items():
            io.show_system(f"{char}: {count} votes", style="muted")

        top = max(vote_counts.values()) if vote_counts else 0
        leaders = [c for c, n in vote_counts.items() if n == top]
        if len(leaders) != 1:
            if not vote_counts:
                text = "Nobody cast a vote. The town could not bring itself to hang anyone."
            else:
                text = f"The vote is tied between {', '.join(leaders)}. The town could not agree, so nobody hangs today."
            io.show_system(text, style="warning")
            state.public_events.append(f"Day {state.day} Voting: {text}")
            state.last_verdict = {"day": state.day, "hanged": None, "text": text, "drew_votes": drew_votes}
            io.pause()
            state.phase = GamePhase.AFTERMATH
            return

        lynched_char = leaders[0]
        io.show_death(lynched_char, "lynched")
        self._final_words(lynched_char)

        state.alive_characters.remove(lynched_char)
        text = f"{lynched_char} was hanged by the town. Their true allegiance is unknown."
        state.public_events.append(f"Day {state.day} Voting: {lynched_char} was lynched by the town.")
        state.last_verdict = {"day": state.day, "hanged": lynched_char, "text": text, "drew_votes": drew_votes}

        if state.is_coroner_alive():
            lynched_role = state.roles.get(lynched_char, "villager")
            allegiance = "werewolf" if lynched_role == "werewolf" else "innocent"
            coroner_name = next(n for n in state.alive_characters if state.roles.get(n) == "coroner")
            finding = f"Day {state.day}: {lynched_char} was {allegiance}"
            state.coroner_knowledge.append(finding)
            gm.stat_engine.process_coroner_findings(finding)
            if coroner_name == "Player":
                io.show_system(
                    f"CORONER INSIGHT: You examine the body — {lynched_char} was {allegiance.upper()}.",
                    style="special"
                )

        if lynched_char == "Player":
            gm.end_game("player_lynched")
            return
        result = state.check_win_condition()
        if result:
            gm.end_game(result)
            return

        io.pause()
        state.phase = GamePhase.AFTERMATH
