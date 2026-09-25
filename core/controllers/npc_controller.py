import random
from difflib import SequenceMatcher

from core.game_state import PREMISE
from models.clues import plan_scene

from services.prompt_service import NPC_INTENTS, NPC_REACTION_INTENTS, VALID_EMOTIONS


class NPCController:
    def __init__(self, gm):
        self.gm = gm

    def calculate_bids(self, multipliers: dict) -> str:
        """Calculates which NPC speaks next."""
        npc_names = [name for name in self.gm.state.alive_characters if name != "Player"]
        if not npc_names:
            return None

        weights = []
        for name in npc_names:
            char_obj = self.gm.characters[name]
            weight = char_obj.assertion_drive * multipliers.get(name, 1.0)
            weights.append(weight)

        chosen_speaker = random.choices(npc_names, weights=weights, k=1)[0]
        return chosen_speaker

    def build_reaction_queue(self, primary_speaker: str, target: str) -> list[str]:
        """Picks who gets a chance to react: the target first, then NPCs with a stake read off
        their allegiance tables (the target's friends and packmates before anyone who merely
        knows the speaker or target), then one random bystander. Each may still stay silent."""
        alive_npcs = [n for n in self.gm.state.alive_characters if n not in ("Player", primary_speaker)]
        queue = [target] if target in alive_npcs else []

        def stake(npc):
            book = self.gm.state.logbooks.get(npc)
            if not book:
                return 0
            if target in book.pack or book.relation_to(target) == "friend":
                return 2
            involved = [n for n in (primary_speaker, target) if n not in ("None", "Player")]
            return 1 if any(book.relation_to(n) or n in book.pack for n in involved) else 0

        others = [n for n in alive_npcs if n not in queue]
        random.shuffle(others)
        others.sort(key=stake, reverse=True)
        concerned = [n for n in others if stake(n) > 0]
        bystanders = [n for n in others if stake(n) == 0]

        cap = self.gm.config.get("max_reactions_per_assertion", 3)
        return (queue + concerned + bystanders[:1])[:max(cap, len(queue))]

    # ================================================================
    # LOGBOOKS
    # ================================================================

    def write_opening_entry(self, name: str):
        """Has a character explain their starting friends and enemies in their own logbook."""
        char_obj = self.gm.characters[name]
        book = self.gm.state.logbooks[name]
        others_text = "\n".join(
            f"- {c.name}: {c.occupation}. {c.bio}"
            for c in self.gm.characters.values() if c.name != name
        )
        system = self._system_prompt(name)
        prompt = self.gm.prompt_builder.build_logbook_seed_prompt(
            character=char_obj,
            friends=book.friends,
            enemies=book.enemies,
            others_text=others_text,
            situation=self.gm.state.morning_event,
        )
        entry = self.gm.llm.generate_text(system, prompt)
        book.add_entry(self.gm.state.day, "Prologue", entry.strip().strip('"'))

    def write_entry(self, name: str, moment: str, facts: list[str]):
        """Adds an in-character entry about `facts` and lets the character revise their friends and
        enemies. Meant to run in the background (see GameMaster.background)."""
        state = self.gm.state
        book = state.logbooks.get(name)
        if not book or not facts or name not in state.alive_characters:
            return
        names = [n for n in self.gm.characters if n != name] + ["Player"]
        prompt = self.gm.prompt_builder.build_logbook_entry_prompt(self.gm.characters[name], moment, facts, names)
        data = self.gm.llm.generate_json(self._system_prompt(name), prompt, use_narrative_cfg=True) or {}
        entry = str(data.get("entry", "")).strip().strip('"')
        if not entry:
            return
        book.add_entry(state.day, moment, entry)
        friends, enemies = data.get("friends"), data.get("enemies")
        if isinstance(friends, list) and isinstance(enemies, list):
            clean = lambda xs: [self.gm.sanitize_target(str(x), pool=names) for x in xs]
            book.set_allegiances(clean(friends), clean(enemies), names)

    def compact_logbook(self, name: str):
        """Folds a character's memory and entries into a short memory. Runs in the background."""
        book = self.gm.state.logbooks.get(name)
        if not book or not book.entries:
            return
        cfg = self.gm.logbook_config
        prompt = self.gm.prompt_builder.build_compaction_prompt(
            self.gm.characters[name], book.render(alive=self.gm.state.alive_characters),
            cfg.get("memory_sentences", 6))
        memory = self.gm.llm.generate_text(self._system_prompt(name), prompt)
        book.compact(memory.strip().strip('"'))

    def day_facts(self, name: str) -> list[str]:
        """What happened today that concerns this character, routed through their allegiance table."""
        state = self.gm.state
        book = state.logbooks.get(name)
        if not book:
            return []
        facts = self._concerns(name)
        ballots = state.votes_by_day.get(state.day, {})
        mine = ballots.get(name)
        if mine and mine != "None":
            facts.append(f"You voted to hang {mine}.")
        against_me = [v for v, t in ballots.items() if t == name]
        if against_me:
            facts.append(f"{', '.join(against_me)} voted to hang you.")
        for voter, target in ballots.items():
            if voter == name or target in (None, "None", name):
                continue
            relation = "packmate" if target in book.pack else book.relation_to(target)
            if relation:
                facts.append(f"{voter} voted to hang your {relation} {target}.")
        if state.last_verdict and state.last_verdict["day"] == state.day:
            facts.append(state.last_verdict["text"])
        return facts

    # ================================================================
    # REVEAL PIPELINE (called between assertions, not from bids)
    # ================================================================

    def generate_reveal(self, speaker_name: str, engine_result: dict) -> dict:
        """Generates LLM dialogue for a reveal. Called with the engine result from check_all_reveals."""
        char_obj = self.gm.characters[speaker_name]
        role = self.gm.state.roles.get(speaker_name, "villager")
        return self._handle_role_reveal(speaker_name, char_obj, role, engine_result)

    # ================================================================
    # SHARED PROMPT PIECES
    # ================================================================

    def _system_prompt(self, name: str) -> str:
        """Role-aware system prompt with the character's private logbook."""
        state = self.gm.state
        role = state.roles.get(name, "villager")
        return self.gm.prompt_builder.build_system_prompt(
            self.gm.characters[name], role if state.roles_known else None,
            known_werewolves=[n for n, r in state.roles.items() if r == "werewolf" and n in state.alive_characters],
            coroner_knowledge=state.coroner_knowledge if role == "coroner" else None,
            ga_protection_history=state.ga_protection_history if role == "guardian_angel" else None,
            logbook_text=self.gm.get_logbook_text(name),
        )

    def _context_kwargs(self, name: str) -> dict:
        return {
            "character": self.gm.characters[name],
            "day": self.gm.state.day,
            "game_context": self.gm.get_game_context(),
            "roster_text": self.gm.get_roster_text(viewer=name),
            "claims_text": self.gm.get_claims_text(),
            "record_text": self.gm.get_public_record_text(),
            "chat_history": list(self.gm.state.chat_history),
            "history_window": self.gm.config.get("chat_history_window", 8),
        }

    def _stakes_text(self, name: str, speaker: str = None, target: str = None) -> str:
        """Engine-routed facts that concern this character personally (see _concerns), joined for a prompt."""
        return "\n".join(self._concerns(name, speaker, target))

    def _concerns(self, name: str, speaker: str = None, target: str = None) -> list[str]:
        """Facts that concern this character personally, read off their allegiance table: attacks on
        them, their friends, enemies or packmates today, and how they relate to whoever is speaking now."""
        book = self.gm.state.logbooks.get(name)
        if not book:
            return []
        lines, described = [], set()
        today = [r for r in self.gm.state.public_record if r["day"] == self.gm.state.day]
        for r in today[-10:]:
            if r["intent"] not in ("accuse", "question", "defend_other") or r["speaker"] == name:
                continue
            verb = {"accuse": "accused", "question": "questioned", "defend_other": "defended"}[r["intent"]]
            who = r["target"]
            if who == name:
                lines.append(f"{r['speaker']} {verb} you.")
            elif who in book.pack:
                lines.append(f"{r['speaker']} {verb} your packmate {who}.")
                described.add(who)
            elif book.relation_to(who):
                lines.append(f"{r['speaker']} {verb} your {book.relation_to(who)} {who}.")
                described.add(who)

        for who in (speaker, target):
            if who in (None, "None", name, "Player") or who in described:
                continue
            if who in book.pack:
                lines.append(f"{who} is your fellow werewolf (secret).")
            elif book.relation_to(who):
                lines.append(f"{who} is your {book.relation_to(who)}.")
        return list(dict.fromkeys(lines))

    TARGETED_INTENTS = {"accuse", "question", "defend_other", "agree", "disagree"}

    def _validate_decision(self, data: dict, name: str, allowed: str, fallback_target: str = "None") -> dict:
        """Turns the model's JSON into a legal action: a known intent, a living target that
        isn't the speaker (or None), a known emotion, and a cleaned-up line of dialogue."""
        data = data or {}
        intent = str(data.get("intent", "neutral")).strip().lower().replace(" ", "_").replace("-", "_")
        target = self.gm.sanitize_target(str(data.get("target", "None")))
        dialogue = str(data.get("dialogue") or "").strip().strip('"').strip()

        if intent == "defend":
            intent = "defend_other" if target not in ("None", name) else "defend_self"
        if intent not in allowed.split("|"):
            intent = "neutral"
        if target == name:
            target = "None"
            if intent == "defend_other":
                intent = "defend_self"

        if intent in self.TARGETED_INTENTS and target == "None":
            if intent in ("agree", "disagree") and fallback_target not in ("None", name):
                target = fallback_target
            else:
                found = self.gm.sanitize_target(dialogue) if dialogue else "None"
                if found not in ("None", name):
                    target = found
                else:
                    intent = "neutral"
        if intent not in self.TARGETED_INTENTS:
            target = "None"

        emotion = str(data.get("emotion", "neutral")).strip().lower()
        if emotion not in VALID_EMOTIONS.split("|"):
            emotion = "neutral"

        return {
            "intent": intent,
            "target": target,
            "emotion": emotion,
            "reasoning": str(data.get("thought", "")).strip(),
            "dialogue": dialogue,
        }

    def _decide(self, name: str, prompt: str, allowed: str, fallback_target: str = "None") -> dict:
        """One LLM call that decides and speaks, validated. If the line nearly repeats something
        this character already said, retries once naming that line (small models otherwise
        loop on their stock sayings)."""
        system = self._system_prompt(name)
        result = self._validate_decision(
            self.gm.llm.generate_json(system, prompt, True), name, allowed, fallback_target)
        repeated = self._repeated_line(name, result["dialogue"])
        if repeated:
            retry = prompt + f'\n\nYou already said: "{repeated}". Say something different this time.'
            result = self._validate_decision(
                self.gm.llm.generate_json(system, retry, True), name, allowed, fallback_target)
        return result

    def _repeated_line(self, name: str, dialogue: str) -> str | None:
        """Returns the earlier line of this character's (or one of their example lines, which are
        style references only) that `dialogue` nearly repeats, if any."""
        if not dialogue:
            return None
        own = [r["dialogue"] for r in self.gm.state.public_record if r["speaker"] == name and r.get("dialogue")]
        examples = [line for per_intent in self.gm.characters[name].speech_examples.values()
                    if isinstance(per_intent, dict) for line in per_intent.values() if "{target}" not in line]
        for line in own[-5:] + examples:
            if SequenceMatcher(None, dialogue.lower(), line.lower()).ratio() >= 0.7:
                return line
        return None

    # ================================================================
    # ASSERTION PIPELINE: one LLM call decides and speaks, the engine validates
    # ================================================================

    def generate_assertion(self, speaker_name: str, current_assertion: int) -> dict:
        """Pure generation — no state mutations, no display. Caller applies side effects."""
        prompt = self.gm.prompt_builder.build_assertion_prompt(
            stakes_text=self._stakes_text(speaker_name),
            **self._context_kwargs(speaker_name),
        )
        result = self._decide(speaker_name, prompt, NPC_INTENTS)
        if not result["dialogue"]:
            result.update(intent="neutral", target="None", dialogue="... (Glares in silence)")
        return result

    # ================================================================
    # REACTION PIPELINE: one LLM call decides whether and how to react
    # ================================================================

    def process_reaction(self, primary_speaker: str, assertion_data: dict,
                         reactor_name: str, current_assertion: int,
                         reaction_chain: list = None):
        """Pure generation — no state mutations, no display. Caller applies side effects.
        Returns None when the reactor chooses to stay silent.

        Args:
            primary_speaker: The original asserter's name.
            assertion_data: The original assertion that started this reaction chain.
            reactor_name: Who is reacting.
            current_assertion: Index of current assertion round.
            reaction_chain: List of {speaker, dialogue, intent} dicts for reactions so far.
        """
        speaker_target = assertion_data.get("target", "None")
        prompt = self.gm.prompt_builder.build_reaction_prompt(
            assertion_speaker=primary_speaker,
            assertion_target=speaker_target,
            assertion_dialogue=assertion_data.get("dialogue", "..."),
            reaction_chain=list(reaction_chain or []),
            stakes_text=self._stakes_text(reactor_name, primary_speaker, speaker_target),
            **self._context_kwargs(reactor_name),
        )
        result = self._decide(reactor_name, prompt, NPC_REACTION_INTENTS, fallback_target=primary_speaker)
        if result["intent"] == "silent" or not result["dialogue"]:
            return None

        result["primary_speaker"] = primary_speaker
        result["intensity"] = "high" if speaker_target == reactor_name else "medium"
        return result

    # ================================================================
    # MORNING & AFTERMATH
    # ================================================================

    def build_crime_scene(self, victim: str) -> str:
        """What the village finds in the morning. The engine fixes the place and the traces (a vague true
        clue sometimes, a red herring usually), the LLM writes the scene around them. The wolves learn
        which trace points their way; the Coroner learns which one was planted."""
        state = self.gm.state
        cfg = self.gm.crime_scene_config
        location, clues = plan_scene(state.day, victim, state.killer_last_night, state.roles,
                                     state.alive_characters, self.gm.characters, cfg)
        for clue in clues:
            state.clues.add(clue)

        occupation = self.gm.characters[victim].occupation.lower() if victim in self.gm.characters else "traveler"
        prompt = self.gm.prompt_builder.build_crime_scene_prompt(
            victim, f"the {occupation}", location, [c.tag for c in clues], PREMISE)
        scene = self.gm.llm.generate_text(
            "You are the narrator of a dark village mystery. You write vivid, grounded prose.", prompt).strip()
        if not scene:
            traces = f" Beside the body: traces of {' and '.join(c.tag for c in clues)}." if clues else ""
            scene = f"{victim}, the {occupation}, was found dead at {location}, torn apart.{traces}"

        self._share_scene_secrets(victim, clues)
        return scene

    def _share_scene_secrets(self, victim: str, clues: list):
        """Private knowledge about the scene: the wolves know which trace points at them, the Coroner
        learns which trace was planted (evidence, never the killer)."""
        state = self.gm.state
        true_clue = next((c for c in clues if c.kind == "true"), None)
        herring = next((c for c in clues if c.kind == "herring"), None)
        wolves = [n for n, r in state.roles.items() if r == "werewolf" and n in state.alive_characters]
        if true_clue:
            others = [f for f in true_clue.fits if f not in wolves]
            note = (f"The {true_clue.tag} found by {victim}'s body could lead back to the pack. "
                    f"{', '.join(others)} could have left it too, which is useful.")
            for wolf in wolves:
                if wolf in state.logbooks:
                    state.logbooks[wolf].add_entry(state.day, "Morning", note)
            if "Player" in wolves:
                self.gm.io.show_system(note, style="special")

        coroner = next((n for n in state.alive_characters if state.roles.get(n) == "coroner"), None)
        if coroner and herring:
            finding = (f"Day {state.day}: examining {victim}'s body, I found that the {herring.tag} "
                       f"was planted after death")
            state.coroner_knowledge.append(finding)
            if coroner in state.logbooks:
                state.logbooks[coroner].add_entry(state.day, "Morning", finding + ". Someone wants us looking the wrong way.")
            if coroner == "Player":
                self.gm.io.show_system(f"CORONER INSIGHT: {finding}.", style="special")

    def react_to_verdict(self, name: str, verdict_text: str, chain: list) -> dict | None:
        """A character's reaction once the vote is over. None when they stay silent."""
        state = self.gm.state
        votes = [e for e in state.public_events if e.startswith(f"Day {state.day} votes:")]
        kwargs = self._context_kwargs(name)
        prompt = self.gm.prompt_builder.build_aftermath_prompt(
            verdict_text=verdict_text,
            votes_text=votes[-1] if votes else "",
            reaction_chain=list(chain),
            stakes_text=self._stakes_text(name),
            **kwargs,
        )
        result = self._decide(name, prompt, NPC_REACTION_INTENTS)
        if result["intent"] == "silent" or not result["dialogue"]:
            return None
        return result

    # ================================================================
    # ROLE REVEALS & MORNING REPORTS
    # ================================================================

    def _handle_role_reveal(self, speaker_name: str, char_obj, role: str, engine_result: dict) -> dict:
        """Pure generation for role reveals — no state mutations."""
        claimed_role = engine_result["claimed_role"]
        findings = engine_result.get("findings", [])
        is_pressure = engine_result.get("intensity") == "high" and "counter" in engine_result.get("engine_reasoning", "")

        ROLE_LABELS = {"guardian_angel": "Guardian Angel", "coroner": "Coroner"}
        label = ROLE_LABELS.get(claimed_role, claimed_role)

        # Build system prompt (role-aware so the actor knows if they're lying)
        system_prompt = self._system_prompt(char_obj.name)

        reveal_prompt = self.gm.prompt_builder.build_role_reveal_prompt(
            character_name=speaker_name,
            claimed_role=claimed_role,
            findings=findings,
            chat_history=self.gm.state.chat_history,
            is_pressure=is_pressure,
            character=char_obj,
        )

        raw_dialogue = self.gm.llm.generate_text(system_prompt, reveal_prompt).strip().strip('"') or f"I am the {label}."

        return {
            "dialogue": raw_dialogue,
            "intent": "reveal_role",
            "target": "None",
            "emotion": engine_result.get("emotion", "arrogant"),
            "reasoning": engine_result["engine_reasoning"],
            "claimed_role": claimed_role,
            "findings": findings,
            "_fake_claim": engine_result.get("_fake_claim"),
        }

    def generate_morning_report(self, speaker_name: str) -> str | None:
        """Generates a morning report for a revealed role holder. Returns dialogue or None."""
        char_obj = self.gm.characters.get(speaker_name)
        if not char_obj:
            return None

        claimed_role = self.gm.state.revealed_roles.get(speaker_name)
        if not claimed_role:
            return None

        real_role = self.gm.state.roles.get(speaker_name, "villager")

        # Determine new findings since last report
        if real_role == claimed_role:
            # Real role holder: share actual new findings
            new_findings = self._get_new_findings(speaker_name, real_role)
        elif real_role == "werewolf":
            # Fake claim: fabricate findings
            new_findings = self.gm.stat_engine._fabricate_findings(speaker_name, claimed_role)
        else:
            return None

        if not new_findings:
            return None

        system_prompt = self._system_prompt(char_obj.name)

        report_prompt = self.gm.prompt_builder.build_morning_report_prompt(
            character_name=speaker_name,
            claimed_role=claimed_role,
            new_findings=new_findings,
            chat_history=self.gm.state.chat_history,
            character=char_obj,
        )

        dialogue = self.gm.llm.generate_text(system_prompt, report_prompt).strip().strip('"') or None
        return dialogue

    def _get_new_findings(self, name: str, role: str) -> list[str]:
        """Gets findings from the most recent night only."""
        day = self.gm.state.day
        if role == "guardian_angel":
            return [f for f in self.gm.state.ga_protection_history if f.startswith(f"Night {day - 1}")]
        elif role == "coroner":
            return [f for f in self.gm.state.coroner_knowledge if f.startswith(f"Day {day - 1}")]
        return []

    # ================================================================
    # GROUP DECISIONS — votes and night actions, one LLM call per side
    # ================================================================
    # Villagers and wolves are decided in separate calls so the model never
    # knows who the wolves are while reasoning for the village. Anything the
    # model gets wrong or leaves out falls back to the stat engine.

    ROLE_LABELS = {"villager": "a villager", "werewolf": "a werewolf",
                   "guardian_angel": "the Guardian Angel", "coroner": "the Coroner"}

    def _brief(self, name: str) -> str:
        state = self.gm.state
        role = state.roles.get(name, "villager")
        knowledge = []
        role_label = self.ROLE_LABELS.get(role, role)
        if role == "werewolf":
            pack = [w for w, r in state.roles.items() if r == "werewolf" and w != name and w in state.alive_characters]
            role_label += f", packmate of {', '.join(pack)}" if pack else ", the last of the pack"
        elif role == "guardian_angel" and state.ga_protection_history:
            knowledge.append("protected so far: " + "; ".join(state.ga_protection_history))
        elif role == "coroner" and state.coroner_knowledge:
            knowledge.append("coroner findings: " + "; ".join(state.coroner_knowledge))
        book = state.logbooks.get(name)
        logbook = book.render(alive=state.alive_characters, max_entries=3) if book else ""
        return self.gm.prompt_builder.build_character_brief(
            self.gm.characters[name], role_label, knowledge, logbook)

    def _shared_kwargs(self) -> dict:
        return {
            "game_context": self.gm.get_game_context(),
            "roster_text": self.gm.get_roster_text(),
            "claims_text": self.gm.get_claims_text(),
            "transcript": self.gm.get_day_transcript(),
        }

    def _group_call(self, prompt: str, varied: bool = False) -> dict:
        """Low temperature by default; `varied` uses the narrative sampling so a retry can differ."""
        system = self.gm.prompt_builder.build_group_decision_system()
        return self.gm.llm.generate_json(system, prompt, use_narrative_cfg=varied) or {}

    def _note_fallback(self, what: str, data: dict):
        """Under show_logic, says when the engine had to stand in for the LLM, with the raw answer."""
        if self.gm.debug.get("show_logic"):
            raw = str(data)[:300]
            self.gm.io.show_system(f"{what} fell back to the stat engine. LLM answer: {raw}", style="muted")

    @staticmethod
    def _vote_entries(data: dict) -> list[dict]:
        """Accepts {"votes": [{voter, vote, reasoning}]} and the {"votes": {voter: {...}}} variant."""
        votes = data.get("votes", [])
        if isinstance(votes, dict):
            votes = [{"voter": k, **v} if isinstance(v, dict) else {"voter": k, "vote": v} for k, v in votes.items()]
        return [v for v in votes if isinstance(v, dict)] if isinstance(votes, list) else []

    def decide_votes(self, voters: list[str]) -> dict:
        """Returns {voter: {"target", "thought_process"}} for every NPC voter."""
        state = self.gm.state
        wolves = [v for v in voters if state.roles.get(v) == "werewolf"]
        village = [v for v in voters if v not in wolves]
        pack = [n for n in state.alive_characters if state.roles.get(n) == "werewolf"]

        results = {}
        for group, group_pack in ((village, None), (wolves, pack)):
            if group:
                results.update(self._decide_group_votes(group, group_pack))
        for voter in voters:
            if voter not in results:
                results[voter] = self.gm.stat_engine.compute_vote(voter)
        return results

    def _decide_group_votes(self, group: list[str], pack: list[str] = None) -> dict:
        """One call for a side. Illegal votes (self, or a packmate for wolves) get one retry that
        names the mistake; whatever is still missing is left for the engine."""
        state = self.gm.state
        candidates = [n for n in state.alive_characters if n not in (pack or [])]
        briefs = [self._brief(v) for v in group]
        if pack:
            briefs = [b + f"May vote for: {', '.join(candidates)}, None (never {', '.join(p for p in pack if p != v)})\n"
                      for b, v in zip(briefs, group)]
        prompt = self.gm.prompt_builder.build_vote_prompt(
            briefs=briefs, candidates=candidates, pack=pack, **self._shared_kwargs(),
        )

        results, data = {}, {}
        for attempt in range(2):
            data = self._group_call(prompt, varied=attempt > 0)
            mistakes = []
            for entry in self._vote_entries(data):
                voter = self.gm.sanitize_target(str(entry.get("voter", "")))
                if voter not in group or voter in results:
                    continue
                target = self.gm.sanitize_target(str(entry.get("vote", "None")))
                if target == voter or (pack and target in pack):
                    who = "themselves" if target == voter else f"{target}, their own packmate"
                    mistakes.append(f"{voter} voted for {who}")
                    continue
                results[voter] = {"target": target, "thought_process": str(entry.get("reasoning", "")).strip()}
            if all(v in results for v in group) or not mistakes:
                break
            prompt += (f"\n\nYour last answer was invalid: {'; '.join(mistakes)}. "
                       f"Choose again for every voter, only from the valid votes.")

        missing = [v for v in group if v not in results]
        if missing:
            self._note_fallback(f"Votes of {', '.join(missing)}", data)
        return results

    def decide_kill(self, wolves: list[str], candidates: list[str]) -> dict:
        """The NPC wolves pick a victim together. Returns {"target", "reasoning", "whispers": {wolf: text}}.
        With the Player in the pack the whispers are advice and the Player makes the call."""
        npc_wolves = [w for w in wolves if w != "Player"]
        if not npc_wolves or not candidates:
            return {"target": random.choice(candidates) if candidates else "None", "reasoning": "",
                    "whispers": {}, "killer": wolves[0] if wolves else None}

        prompt = self.gm.prompt_builder.build_kill_prompt(
            briefs=[self._brief(w) for w in npc_wolves], candidates=candidates, **self._shared_kwargs(),
        )
        data = self._group_call(prompt)
        whispers, preferences = {}, {}
        for entry in data.get("whispers", []) or []:
            if isinstance(entry, dict):
                wolf = self.gm.sanitize_target(str(entry.get("wolf", "")))
                if wolf in npc_wolves and entry.get("whisper"):
                    whispers[wolf] = str(entry["whisper"]).strip().strip('"')
                if wolf in npc_wolves:
                    preferences[wolf] = self.gm.sanitize_target(str(entry.get("preference", "")))

        target = self.gm.sanitize_target(str(data.get("target", "None")))
        if target not in candidates:
            self._note_fallback("The pack's kill", data)
            target = self.gm.stat_engine.compute_kill_preference(npc_wolves[0], candidates)["target"]
        # The wolf whose preference carried the night did the deed (and may have left traces)
        killer = next((w for w, p in preferences.items() if p == target), random.choice(npc_wolves))
        return {"target": target, "reasoning": str(data.get("reasoning", "")).strip(), "whispers": whispers,
                "killer": killer}

    def decide_protection(self, ga_name: str, candidates: list[str]) -> dict:
        """The NPC Guardian Angel picks who to protect. Returns {"target", "thought_process"}."""
        excluded = [n for n in self.gm.state.alive_characters if n not in candidates and n != ga_name]
        prompt = self.gm.prompt_builder.build_protect_prompt(
            brief=self._brief(ga_name), candidates=candidates, excluded=excluded, **self._shared_kwargs(),
        )
        data = self._group_call(prompt)
        target = self.gm.sanitize_target(str(data.get("target", "None")))
        if target not in candidates:
            self._note_fallback(f"{ga_name}'s protection", data)
            return self.gm.stat_engine.compute_protect_preference(ga_name, candidates)
        return {"target": target, "thought_process": str(data.get("reasoning", "")).strip()}

    # ================================================================
    # FINAL WORDS — kept as LLM call (emotional impact)
    # ================================================================

    def generate_final_words(self, character_name: str) -> str:
        char_obj = self.gm.characters[character_name]
        role = self.gm.state.roles.get(character_name, "villager")
        system_prompt = self._system_prompt(char_obj.name)

        user_prompt = self.gm.prompt_builder.build_final_words_prompt(
            character_name=character_name,
            secret_role=role,
            alive_characters=self.gm.state.alive_characters,
            chat_history=self.gm.state.chat_history,
            character=char_obj,
        )

        dialogue = self.gm.llm.generate_text(system_prompt, user_prompt)
        return dialogue if dialogue else "..."
