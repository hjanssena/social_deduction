import os
import re
from datetime import datetime

from core.controllers.npc_controller import NPCController
from core.controllers.player_controller import PlayerController
from core.game_state import GameState, GamePhase, WIN_MESSAGES
from core.stat_engine import StatEngine
from core.colors import assign_colors
from core.io_handler import IOHandler
from core.phases import (ArrivalPhase, NightPhase, MorningPhase, DiscussionPhase, VotingPhase,
                         AftermathPhase, ChatsPhase)


class GameMaster:
    def __init__(self, llm_service, prompt_service, characters, config, io=None):
        self.llm = llm_service
        self.prompt_builder = prompt_service
        self.config = config.get("discussion", {})
        self.debug = config.get("debug", {})
        self.logbook_config = config.get("logbook", {})
        self.log_dir = os.path.join("logs", datetime.now().strftime("%Y%m%d-%H%M%S"))
        self.io = io or IOHandler()
        self.characters = {c.name: c for c in characters}
        if config.get("display", {}).get("character_colors", True):
            self.io.set_colors(assign_colors(characters))
        self.state = GameState(characters, config)

        # Sub-systems
        self.stat_engine = StatEngine(self.state, self.characters, config.get("engine", {}))
        self.player_controller = PlayerController(self)
        self.npc_controller = NPCController(self)

        # Phase handlers
        self.phases = {
            GamePhase.ARRIVAL: ArrivalPhase(self),
            GamePhase.NIGHT: NightPhase(self),
            GamePhase.MORNING: MorningPhase(self),
            GamePhase.DISCUSSION: DiscussionPhase(self),
            GamePhase.VOTING: VotingPhase(self),
            GamePhase.AFTERMATH: AftermathPhase(self),
            GamePhase.CHATS: ChatsPhase(self),
        }

    def run_loop(self):
        """The main execution loop that routes to specific phase handlers."""
        self.io.show_system("Starting Game Loop...", style="info")

        while self.state.phase != GamePhase.GAME_OVER:
            handler = self.phases.get(self.state.phase)
            if handler:
                handler.run()
                self.dump_logbooks()
            else:
                self.io.show_system(f"Phase {self.state.phase} not implemented yet.", style="error")
                break

    def end_game(self, result: str):
        """Ends the game: the outcome from the Player's side, every role revealed, logbooks saved.
        result: village_wins | werewolves_win | player_killed | player_lynched."""
        state = self.state
        state.phase = GamePhase.GAME_OVER
        state.game_result = result
        player_is_wolf = state.roles.get("Player") == "werewolf"
        if result in ("player_killed", "player_lynched"):
            headline = ("[DEFEAT] You were murdered by the werewolves in your sleep." if result == "player_killed"
                        else "[DEFEAT] The town has hanged you.")
        else:
            won = (result == "werewolves_win") == player_is_wolf
            headline = ("[VICTORY] " if won else "[DEFEAT] ") + WIN_MESSAGES[result]
        self.io.show_game_over(result, headline)
        self.io.show_final_roles(state.roles, state.alive_characters)
        self.dump_logbooks(force=True)
        self.io.show_system(f"Every character's logbook is saved in {self.log_dir}/", style="info")

    # --- Logbooks ---

    def get_logbook_text(self, name: str) -> str:
        """Renders a character's private logbook for their prompts."""
        book = self.state.logbooks.get(name)
        if not book:
            return ""
        max_entries = self.logbook_config.get("max_entries_in_prompt", 12)
        return book.render(alive=self.state.alive_characters, max_entries=max_entries)

    def dump_logbooks(self, force: bool = False):
        """Writes every logbook to logs/<game>/<name>.md when debug.dump_logbooks is on (or forced)."""
        if not (force or self.debug.get("dump_logbooks")):
            return
        os.makedirs(self.log_dir, exist_ok=True)
        for name, book in self.state.logbooks.items():
            filename = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") + ".md"
            with open(os.path.join(self.log_dir, filename), "w") as f:
                f.write(book.to_markdown() + "\n")

    # --- Shared helpers used by controllers and phases ---

    def get_roster_text(self, viewer: str = None) -> str:
        """Builds a brief summary of everyone currently alive. For an NPC viewer each entry is
        tagged with how their logbook sees that person; otherwise with engine opinions."""
        book = self.state.logbooks.get(viewer) if viewer else None
        viewer_opinions = self.state.opinions.get(viewer, {}) if viewer else {}
        roster = []
        for name in self.state.alive_characters:
            if name == "Player":
                entry = "- Player: A traveler that arrived just to stay the night."
            else:
                char_obj = self.characters.get(name)
                if not char_obj:
                    continue
                entry = f"- {name}: {char_obj.occupation.capitalize()}."

            if viewer and name == viewer:
                entry += " (you)"
            elif book:
                if name in book.pack:
                    entry += " (fellow werewolf - secret)"
                elif book.relation_to(name):
                    entry += f" (your {book.relation_to(name)})"
            elif viewer:
                opinion = viewer_opinions.get(name)
                if opinion:
                    entry += f" ({opinion})"
            roster.append(entry)
        return "\n".join(roster)

    # --- Public record: who did what to whom, as everyone in the room saw it ---

    RECORD_PHRASES = {
        "accuse": "accused {target}",
        "question": "questioned {target}",
        "defend_other": "defended {target}",
        "defend_self": "denied the accusations",
        "agree": "agreed with {target}",
        "disagree": "disagreed with {target}",
        "deflect": "dodged and changed the subject",
        "neutral": "shared a general thought",
    }

    def record_action(self, speaker: str, intent: str, target: str = "None", note: str = "", dialogue: str = ""):
        """Adds a public action (assertion, reaction or claim) to today's record."""
        self.state.public_record.append({
            "day": self.state.day, "speaker": speaker, "intent": intent,
            "target": target or "None", "note": note, "dialogue": dialogue,
        })

    def get_day_transcript(self, limit: int = 40) -> str:
        """Today's actions with what was actually said, for the group vote and night prompts."""
        today = [r for r in self.state.public_record if r["day"] == self.state.day][-limit:]
        lines = []
        for r in today:
            aimed = f" -> {r['target']}" if r["target"] != "None" else ""
            said = f': "{r["dialogue"]}"' if r.get("dialogue") else ""
            lines.append(f"- {r['speaker']}{aimed} ({r['intent']}){said}")
        return "\n".join(lines)

    def get_public_record_text(self, limit: int = 15) -> str:
        """Today's public actions, one per line, oldest first."""
        today = [r for r in self.state.public_record if r["day"] == self.state.day][-limit:]
        lines = []
        for r in today:
            if r["note"]:
                action = r["note"]
            else:
                phrase = self.RECORD_PHRASES.get(r["intent"], "spoke")
                if "{target}" in phrase and r["target"] == "None":
                    phrase = phrase.replace(" {target}", "")
                action = phrase.format(target=r["target"])
            lines.append(f"- {r['speaker']} {action}")
        return "\n".join(lines)

    def get_claims_text(self) -> str:
        """Builds a summary of all public role claims and their outcomes."""
        state = self.state
        if not state.revealed_roles:
            return ""

        ROLE_LABELS = {"guardian_angel": "Guardian Angel", "coroner": "Coroner"}
        lines = []
        for name, claimed_role in state.revealed_roles.items():
            label = ROLE_LABELS.get(claimed_role, claimed_role)
            alive = "alive" if name in state.alive_characters else "dead"

            # Check if coroner has verified this person
            verification = None
            for finding in state.coroner_knowledge:
                if name in finding:
                    if "werewolf" in finding:
                        verification = "confirmed werewolf by coroner"
                    elif "innocent" in finding:
                        verification = "confirmed innocent by coroner"

            entry = f"- {name} claimed {label} ({alive})"
            if verification:
                entry += f" [{verification}]"
            lines.append(entry)

        return "\n".join(lines)

    def condense_day_history(self):
        """At the start of a new day, condense the previous day's chat_history into a summary.
        Replaces old entries with the condensed version at the start of the list."""
        state = self.state
        if not state.chat_history:
            return

        # Build condensation prompt
        history_text = "\n".join(state.chat_history)
        system = "You are a concise game narrator. Summarize the key events and accusations."
        prompt = (
            f"Summarize Day {state.day - 1}'s discussion into 3-5 bullet points.\n"
            f"Focus on: who accused whom, who defended whom, any role reveals, and the overall mood.\n"
            f"Use exact character names. Be factual and brief.\n\n"
            f"Discussion:\n{history_text}\n\n"
            f"Respond with ONLY a JSON object:\n"
            f'{{"summary": "<3-5 bullet point summary>"}}'
        )

        result = self.llm.generate_json(system, prompt)
        summary = result.get("summary", "") if result else ""

        if summary:
            # Replace old history with condensed version
            state.chat_history = [f"[Summary of Day {state.day - 1}]: {summary}"]
        # If condensation fails, keep the raw history (better than losing it)

    def get_game_context(self) -> str:
        """Builds a situational summary: the stakes, what the village woke up to, the last verdict."""
        state = self.state
        lines = [
            "Werewolves hide among the villagers. Each day the town talks and votes to hang a suspect; "
            "each night the wolves kill someone.",
            state.morning_event,
        ]
        if state.day > 0:
            if state.last_verdict and state.last_verdict["day"] == state.day - 1:
                lines.append(f"Yesterday: {state.last_verdict['text']}")
            vote_events = [e for e in state.public_events if e.startswith(f"Day {state.day - 1} votes:")]
            if vote_events:
                lines.append(vote_events[-1])
            lines.append(f"It is now Day {state.day}. {len(state.alive_characters)} people remain alive.")
        return " ".join(lines)

    def sanitize_target(self, target: str) -> str:
        """Maps an LLM-supplied target onto a living character's exact name, or 'None'.
        Accepts different casing, extra words ("Silas the scholar"), a first name alone
        ("Sol" for "Sol Badguy") and occupations ("the blacksmith")."""
        target = (target or "None").strip().strip('"\'.')
        if target in self.state.alive_characters or target == "None":
            return target

        target_lower = target.lower()
        if target_lower in ("", "none", "null", "nobody", "room", "everyone"):
            return "None"
        alive = self.state.alive_characters
        for name in alive:
            if name.lower() == target_lower:
                return name
        for name in alive:
            if re.search(rf"\b{re.escape(name.lower())}\b", target_lower):
                return name
        first_names = {}
        for name in alive:
            first_names.setdefault(name.split()[0].lower(), []).append(name)
        for word in re.findall(r"[a-z']+", target_lower):
            if len(first_names.get(word, [])) == 1:
                return first_names[word][0]
        for name in alive:
            if name == "Player":
                continue
            char_obj = self.characters.get(name)
            if char_obj and char_obj.occupation.lower() in target_lower:
                return name

        return "None"
