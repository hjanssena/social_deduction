import threading
import time
from collections import Counter

from core.game_state import GamePhase
from core.trust_manager import TrustManager

VOTE_TIMEOUT_SECONDS = 300
REVEAL_PAUSE_SECONDS = 1.5


class VotingPhase:
    """Collects player and NPC votes in parallel, tallies, and executes the lynch."""

    def __init__(self, gm):
        self.gm = gm

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state

        npc_voters = [name for name in state.alive_characters if name != "Player"]
        npc_vote_results = {}

        # Collect NPC votes in background while player decides
        def process_npc_votes():
            for npc in npc_voters:
                npc_vote_results[npc] = gm.npc_controller.generate_vote(npc)

        vote_thread = threading.Thread(target=process_npc_votes)
        vote_thread.start()

        player_vote = gm.player_controller.get_vote()

        io.display("\n\033[90m[System] You cast your vote. Waiting for the town to finalize their decisions...\033[0m")

        vote_thread.join(timeout=VOTE_TIMEOUT_SECONDS)
        if vote_thread.is_alive():
            io.display("\033[91m[System] NPC voting timed out. Using available votes only.\033[0m")

        # Reveal
        io.display("\n\033[36m" + "="*50)
        io.display("                 THE VERDICT")
        io.display("="*50 + "\033[0m\n")

        all_votes = {"Player": player_vote}
        self._reveal_player_vote(player_vote)
        self._reveal_npc_votes(npc_voters, npc_vote_results, all_votes)

        self._tally_and_execute(all_votes)

    def _reveal_player_vote(self, player_vote):
        io = self.gm.io
        state = self.gm.state

        if player_vote == "None":
            io.display("[Player]: I abstain from voting.")
            state.logical_history.append("Player [neutral] -> Room (Emotion: neutral). Reason: Abstained from voting.")
        else:
            io.display(f"[Player]: My vote is for {player_vote}.")
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

            io.display(f"\033[90m[Thoughts ({npc})]: {thoughts}\033[0m")
            if target == "None":
                io.display(f"[{npc}]: I... I cannot decide. I abstain.")
                state.logical_history.append(
                    f"{npc} [neutral] -> Room (Emotion: fearful). Reason: Abstained from voting."
                )
            else:
                io.display(f"[{npc}]: My vote is for {target}.")
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

        io.display(f"\n\033[36m--- {condemned}'s Final Words ---\033[0m")

        if condemned == "Player":
            last_words = io.prompt("\033[93m[Speak your final words] >\033[0m ")
            if last_words.strip():
                state.chat_history.append(f"[{condemned} -> Room]: {last_words}")
                state.logical_history.append(
                    f"{condemned} [final_words] -> Room (Emotion: desperate). Reason: Last words before execution."
                )
        else:
            last_words = gm.npc_controller.generate_final_words(condemned)
            io.display(f"[{condemned}]: {last_words}")
            state.chat_history.append(f"[{condemned} -> Room]: {last_words}")
            state.logical_history.append(
                f"{condemned} [final_words] -> Room (Emotion: desperate). Reason: Last words before execution."
            )

        io.pause()

    def _tally_and_execute(self, all_votes):
        gm = self.gm
        io = gm.io
        state = gm.state

        io.display("\n\033[93m--- Final Tally ---\033[0m")
        vote_counts = Counter(all_votes.values())
        if "None" in vote_counts:
            del vote_counts["None"]

        if not vote_counts:
            io.display("The town failed to reach a decision. No one is lynched today.")
            state.public_events.append(
                f"Day {state.day} Voting: The town was paralyzed by indecision. No one was hanged."
            )
        else:
            max_votes = max(vote_counts.values())
            tied_characters = [char for char, count in vote_counts.items() if count == max_votes]

            for char, count in vote_counts.items():
                io.display(f"{char}: {count} votes")

            if len(tied_characters) > 1:
                io.display(
                    f"\nThere is a tie between {', '.join(tied_characters)}. "
                    "The town is deadlocked. No one is lynched."
                )
                state.public_events.append(f"Day {state.day} Voting: A tie vote occurred. No one was hanged.")
            else:
                lynched_char = tied_characters[0]
                io.display(f"\n\033[91mThe town has spoken. {lynched_char} is dragged to the gallows...\033[0m")

                # Final words — before execution
                self._final_words(lynched_char)

                state.alive_characters.remove(lynched_char)
                state.public_events.append(f"Day {state.day} Voting: {lynched_char} was lynched by the town.")

                lynched_role = state.roles.get(lynched_char, "villager")
                if lynched_role == "werewolf":
                    io.display(f"\n\033[92m{lynched_char} was a WEREWOLF! The town got one right.\033[0m")
                    state.public_events.append(f"Day {state.day}: {lynched_char} was revealed as a werewolf.")
                else:
                    io.display(f"\n\033[93m{lynched_char} was an innocent villager. The town has made a grave mistake.\033[0m")
                    state.public_events.append(f"Day {state.day}: {lynched_char} was innocent. The real killer is still free.")

                if lynched_char == "Player":
                    io.display("\n\033[91m[GAME OVER] You have been lynched by the town.\033[0m")
                    state.phase = GamePhase.GAME_OVER
                    return

                result = state.check_win_condition()
                if result:
                    from core.game_state import WIN_MESSAGES
                    io.display(WIN_MESSAGES[result])
                    state.phase = GamePhase.GAME_OVER
                    return

        io.pause("\n\033[90m[Press Enter to end the day] >\033[0m ")
        state.phase = GamePhase.NIGHT
