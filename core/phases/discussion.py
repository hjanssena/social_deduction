import copy

from core.discussion_director import DiscussionDirector
from core.game_state import GamePhase
from core.trust_manager import TrustManager
from core.dialogue_cache import DialoguePrefetcher
from models.thread import Thread, Turn


ROLE_LABELS = {"guardian_angel": "Guardian Angel", "coroner": "Coroner"}


class DiscussionPhase:
    """The day's discussion: one conversation about last night's killing (see docs/discussion-threads.md).

    The director (core/discussion_director.py) picks every speaker: whoever was asked or accused answers
    first, then people with a stake in the last lines respond or pass, and when the exchange runs dry
    someone moves it on to another angle of the killing. Role claims are spoken into the same conversation.
    The Player may speak at every turn. Every prompt leads with the day's question and the last two lines.

    The next NPC line is generated in the background while the player reads the current one; typing
    discards it.
    """

    REVEAL_CHECK_EVERY = 4  # lines between checks for a due role claim

    def __init__(self, gm):
        self.gm = gm
        self.reports = []  # this morning's reports from role claimants, part of the day's question
        self.theme = ""
        self.prefetcher = None
        self.prefetched = None  # (name, role) of the turn being generated in the background
        self.pending_reveals = []  # role claims waiting for their moment
        self.angles = 0

    def run(self):
        gm = self.gm
        io = gm.io
        state = gm.state
        self.prefetcher = DialoguePrefetcher()

        io.show_phase("DISCUSSION", state.day)

        if gm.background.pending():
            io.show_system("The villagers gather in the square...", style="muted")
            gm.background.wait_idle()

        # Condense previous day's history + morning reports
        if state.chat_history:
            gm.condense_day_history()
        self._morning_reports()

        # Discussion primer — sets the tone and reminds characters of the stakes
        primer = self._build_day_primer()
        io.show_primer(primer)
        state.chat_history.append(f"[Town Crier]: {primer}")

        self.theme = gm.get_day_theme(self.reports)
        thread = Thread(day=state.day, opener="", topic=self.theme.split("?")[0] + "?")
        state.threads[state.day] = [thread]
        if gm.debug.get("show_threads"):
            io.show_system(f"— today: {thread.topic} —", style="muted")

        director = DiscussionDirector(gm)
        self._discuss(thread, director)

        self.prefetcher.shutdown()
        self._apply_silence_penalty()

        io.show_system("The sun is setting. Discussion ended.", style="warning")
        state.player_actions_today = 0
        state.phase = GamePhase.VOTING

    # ------------------------------------------------------------------
    # The conversation
    # ------------------------------------------------------------------

    def _discuss(self, thread: Thread, director):
        gm = self.gm
        io = gm.io
        since_check = self.REVEAL_CHECK_EVERY  # check for claims before the first line too
        leads_tried = []
        while not director.day_over(thread):
            if since_check >= self.REVEAL_CHECK_EVERY:
                since_check = 0
                self.pending_reveals.extend(gm.stat_engine.check_all_reveals())
            if self.pending_reveals and self._claim(thread, director):
                since_check += 1
                continue

            name, role = director.next_speaker(thread)
            if role == "lead" and name in leads_tried:
                name = director.pick_lead(exclude=tuple(leads_tried + [thread.last.speaker if thread.last else ""]))
            if name is not None and name != "Player":
                self._prefetch(name, role, thread)

            p_input = io.prompt_join()
            if p_input.strip():
                self._discard_prefetch()
                self._player_turn(thread, director, p_input)
                since_check += 1
                continue
            if name is None:
                break
            if name == "Player":
                self._forced_player_answer(thread, director)
                continue

            ready, data = self._take_prefetched(role, name)
            if not ready:
                data = gm.npc_controller.take_turn(name, role, thread, self.theme)
            if data is None:
                if role == "lead":
                    leads_tried.append(name)  # nothing to say: someone else moves it on
                    if len(leads_tried) >= 3:
                        break
                else:
                    thread.add_pass(name)
                continue
            leads_tried = []
            if role == "lead":
                director.led(name)
                self._show_angle(data)
            self._commit_line(name, data)
            if thread.last is None:
                self._display_opening(name, data)
            else:
                self._display_turn(name, data)
            self._add_turn(thread, director, name, data)
            since_check += 1

    def _claim(self, thread: Thread, director) -> bool:
        """Speaks the next due role claim into the conversation. False if none could be made."""
        gm = self.gm
        while self.pending_reveals:
            name, engine_result = self.pending_reveals.pop(0)
            if name not in gm.state.alive_characters:
                continue
            self._discard_prefetch()
            data = gm.npc_controller.generate_reveal(name, engine_result)
            if not data:
                continue
            self._commit_line(name, data)
            self._display_opening(name, data)
            self._add_turn(thread, director, name, data)
            return True
        return False

    def _add_turn(self, thread: Thread, director, name: str, data: dict):
        thread.add(Turn(name, data.get("intent", "neutral"), data.get("target", "None"), data.get("dialogue", "")))
        director.count_turn()

    def _player_turn(self, thread: Thread, director, text: str):
        """The Player speaks into the conversation; if they ask or accuse someone, that person answers next."""
        gm = self.gm
        last = thread.last
        chain = [{"speaker": t.speaker, "dialogue": t.dialogue, "intent": t.intent} for t in thread.turns[-3:]]
        parsed = gm.player_controller.process_reaction(
            text, last.speaker if last else "Room", last.dialogue if last else "", chain)
        target = parsed.get("target", "None")
        gm.state.chat_history.append(f"[Player -> {target if target != 'None' else 'Room'}]: {text}")
        self._add_turn(thread, director, "Player", {"intent": parsed.get("intent", "neutral"),
                                                    "target": target, "dialogue": text})

    def _forced_player_answer(self, thread: Thread, director):
        """The Player was asked or accused: one chance to answer, and silence is noticed. After that,
        the Player isn't pressed again until someone else asks them something."""
        gm = self.gm
        io = gm.io
        thread.player_prompted = True
        asker = thread.last.speaker if thread.last else "Room"
        text = io.prompt_reaction_forced(asker)
        if text.strip():
            self._player_turn(thread, director, text)
            thread.player_prompted = False
            return
        thread.owed = None
        io.show_system("You refused to defend yourself against a direct claim. The town notices your guilt...",
                       style="error")
        gm.record_action("Player", "silent", asker, note=f"said nothing at all when {asker} pressed them")
        thread.player_prompted = False

    def _show_angle(self, data: dict):
        self.angles += 1
        if self.gm.debug.get("show_threads") and data.get("topic"):
            self.gm.io.show_system(f"— angle {self.angles}: {data['topic']} —", style="muted")

    # --- background generation ------------------------------------------------

    def _prefetch(self, name: str, role: str, thread: Thread):
        self.prefetched = (name, role)
        self.prefetcher.submit(self.gm.npc_controller.take_turn, name, role, copy.deepcopy(thread), self.theme)

    def _take_prefetched(self, role: str, name: str) -> tuple[bool, dict | None]:
        """(True, turn) if the prefetched turn is for this speaker and role (the turn is None for a pass),
        else (False, None)."""
        if self.prefetched == (name, role) and self.prefetcher.has_pending():
            self.prefetched = None
            data, _ = self.prefetcher.get()
            return True, data
        self._discard_prefetch()
        return False, None

    def _discard_prefetch(self):
        self.prefetcher.invalidate()
        self.prefetched = None

    # ------------------------------------------------------------------
    # Committing and showing lines
    # ------------------------------------------------------------------

    def _commit_line(self, speaker_name, data):
        """Applies a committed line (any turn, or a role claim): public record, trust and suspicion."""
        gm = self.gm
        state = gm.state
        intent = data["intent"]
        target = data["target"]

        if intent == "reveal_role":
            claimed_role = data["claimed_role"]
            findings = data.get("findings", [])
            label = ROLE_LABELS.get(claimed_role, claimed_role)

            gm.stat_engine.process_duplicate_claim(speaker_name, claimed_role)
            gm.stat_engine.register_reveal(speaker_name, claimed_role)
            gm.stat_engine.apply_reveal_pressure(speaker_name, claimed_role)

            # Record any wolf fake claim
            if data.get("_fake_claim"):
                state.fake_claims.append(data["_fake_claim"])

            state.logical_history.append(
                f"{speaker_name} [reveal_role] -> Room (claimed {label}). Findings: {findings}"
            )
            state.public_events.append(
                f"Day {state.day}: {speaker_name} claimed to be the {label}."
            )
            gm.record_action(speaker_name, "reveal_role", note=f"claimed to be the {label}", dialogue=data.get("dialogue", ""))
        else:
            emotion = data.get("emotion", "neutral")
            reasoning = data.get("reasoning", "")

            gm.stat_engine.log_action(speaker_name, intent, target)
            state.logical_history.append(
                f"{speaker_name} [{intent}] -> {target} (Emotion: {emotion}). Reason: {reasoning}"
            )
            TrustManager.apply_interaction(state, speaker_name, target, intent, gm.characters)
            gm.record_action(speaker_name, intent, target, dialogue=data.get("dialogue", ""))

            # Suspicion updates for public events
            if intent == "deflect" and target == "None":
                gm.stat_engine.update_all_suspicion("deflect_when_accused", source=speaker_name, target="None")
            elif intent == "accuse" and target != "None":
                gm.stat_engine.update_all_suspicion("accusation", source=speaker_name, target=target)

        # Clear reveal pressure after this character has had their chance
        if speaker_name in state.reveal_pressure:
            del state.reveal_pressure[speaker_name]

    def _display_opening(self, speaker_name, data):
        """Shows a thread's opening line (or a role claim) and adds it to the chat history."""
        io = self.gm.io
        state = self.gm.state
        intent = data["intent"]
        dialogue = data.get("dialogue", "...")
        target = data.get("target", "None")
        display_target = target if target != "None" else "Room"

        if self.gm.debug.get("show_logic"):
            emotion = data.get("emotion", "")
            reasoning = data.get("reasoning", "")
            if intent == "reveal_role":
                claimed_role = data.get("claimed_role", "")
                label = ROLE_LABELS.get(claimed_role, claimed_role)
                findings = data.get("findings", [])
                io.show_engine_debug(speaker_name, f"REVEAL as {label}", "Room", "", f"Findings: {findings}")
            else:
                io.show_engine_debug(speaker_name, intent, target, emotion, reasoning)

        if intent == "reveal_role":
            claimed_role = data.get("claimed_role", "")
            label = ROLE_LABELS.get(claimed_role, claimed_role)
            io.show_reveal(speaker_name, label, dialogue)
            state.chat_history.append(f"[{speaker_name} -> Room]: {dialogue}")
        else:
            state.chat_history.append(f"[{speaker_name} -> {display_target}]: {dialogue}")
            io.show_dialogue(speaker_name, display_target, dialogue, intent=intent, emotion=data.get("emotion"))

    def _display_turn(self, speaker_name, data):
        """A line inside a thread, after its opening."""
        io = self.gm.io
        dialogue = data.get("dialogue", "...")
        target = data.get("target", "None")
        display_target = target if target != "None" else "Room"
        if self.gm.debug.get("show_logic"):
            io.show_engine_debug(speaker_name, data["intent"], target, data.get("emotion", ""),
                                 data.get("reasoning", ""))
        io.show_reaction(speaker_name, display_target, dialogue, intent=data["intent"], emotion=data.get("emotion"))
        self.gm.state.chat_history.append(f"[{speaker_name} -> {display_target}]: {dialogue}")

    # ------------------------------------------------------------------
    # Discussion primer
    # ------------------------------------------------------------------

    def _build_day_primer(self) -> str:
        """Builds a context-setting message for the start of each day's discussion."""
        state = self.gm.state
        alive_count = len(state.alive_characters)
        wolf_warning = "There are werewolves among us. We must find them and vote to hang them before nightfall, or more will die."
        if state.killed_last_night:
            opening = f"{', '.join(state.killed_last_night)} was found dead this morning, torn apart by werewolves."
        else:
            opening = "Nobody died last night, but the werewolves are still among us."
        first_day = " Speak now: share what you know, ask your questions, and choose carefully whom to trust." if state.day == 1 else ""
        return f"Townspeople! {opening} {wolf_warning}{first_day} {alive_count} souls remain."

    # ------------------------------------------------------------------
    # Morning reports & silence penalty
    # ------------------------------------------------------------------

    def _morning_reports(self):
        """Revealed role holders report their findings at the start of each day."""
        gm = self.gm
        io = gm.io
        state = gm.state

        for name in list(state.revealed_roles.keys()):
            if name not in state.alive_characters:
                continue
            if name == "Player":
                continue  # Player reports manually

            report = gm.npc_controller.generate_morning_report(name)
            if report:
                claimed_role = state.revealed_roles[name]
                label = ROLE_LABELS.get(claimed_role, claimed_role)
                io.show_report(name, label, report)
                state.chat_history.append(f"[{name} ({label} Report)]: {report}")
                self.reports.append(f"{name} (who claims to be the {label}): {report}")
                state.logical_history.append(
                    f"{name} [morning_report] -> Room. Role: {label}."
                )
                io.pause()

    def _apply_silence_penalty(self):
        """If the player was too quiet today, the town notices: it goes on the public record."""
        gm = self.gm
        min_actions = gm.config.get("player_min_actions", 2)
        if gm.state.player_actions_today < min_actions:
            gm.io.show_system("Your unnatural silence today has bred deep suspicion...", style="error")
            gm.record_action("Player", "silent", note="barely said a word all day, which everyone noticed")
