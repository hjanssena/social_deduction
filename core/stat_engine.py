import random
from core.trust_manager import TrustManager

# --- Reasoning Templates ---
REASONING_TEMPLATES = {
    "accuse": [
        "{target} has been too quiet and evasive",
        "{target}'s story doesn't hold up to scrutiny",
        "Something about {target}'s behavior is deeply suspicious",
        "{target} has been dodging questions all day",
    ],
    "defend_other": [
        "{target} is being unfairly targeted by the room",
        "The case against {target} is built on nothing",
        "{target} has done nothing to deserve this suspicion",
    ],
    "defend_self": [
        "These accusations are baseless and I won't stand for them",
        "I have nothing to hide and my actions prove it",
        "My accusers should explain themselves instead",
    ],
    "agree": [
        "{target} raises a point the room should consider",
        "The evidence supports what {target} is saying",
        "{target} is making sense and the room should listen",
    ],
    "disagree": [
        "{target}'s reasoning has serious holes",
        "I can't accept {target}'s conclusion without more proof",
        "{target} is jumping to conclusions too quickly",
    ],
    "question": [
        "{target} hasn't explained their whereabouts",
        "{target} owes the room an explanation",
        "I want to hear {target} account for themselves",
    ],
    "deflect": [
        "There are bigger concerns than pointing fingers at me",
        "We are losing focus on what really matters here",
        "This line of questioning leads nowhere",
    ],
    "neutral": [
        "The situation is unclear and I need more information",
        "We should proceed carefully before making accusations",
        "Something doesn't feel right but I can't place it yet",
    ],
}

# --- Emotion Maps ---
# (low_logic_vs_emotion, high_logic_vs_emotion) = weighted choice lists
EMOTION_MAP = {
    "accuse":       (["angry"] * 6 + ["suspicious"] * 4,
                     ["suspicious"] * 8 + ["neutral"] * 2),
    "defend_other": (["angry"] * 5 + ["fearful"] * 3 + ["sad"] * 2,
                     ["neutral"] * 7 + ["suspicious"] * 3),
    "defend_self":  (["fearful"] * 7 + ["angry"] * 3,
                     ["suspicious"] * 6 + ["neutral"] * 4),
    "agree":        (["happy"] * 6 + ["neutral"] * 4,
                     ["neutral"] * 8 + ["happy"] * 2),
    "disagree":     (["angry"] * 7 + ["suspicious"] * 3,
                     ["suspicious"] * 7 + ["arrogant"] * 3),
    "question":     (["suspicious"] * 6 + ["neutral"] * 4,
                     ["suspicious"] * 7 + ["neutral"] * 3),
    "deflect":      (["fearful"] * 5 + ["neutral"] * 5,
                     ["neutral"] * 7 + ["arrogant"] * 3),
    "neutral":      (["neutral"] * 7 + ["suspicious"] * 3,
                     ["neutral"] * 8 + ["suspicious"] * 2),
}


class StatEngine:
    """Deterministic + weighted-random decision engine. Replaces LLM logic phase."""

    def __init__(self, game_state, characters: dict, config: dict = None):
        self.state = game_state
        self.characters = characters
        cfg = config or {}
        self.c_sus = cfg.get("suspicion", {})
        self.c_kill = cfg.get("kill", {})
        self.c_protect = cfg.get("protect", {})
        self.c_assert = cfg.get("assertion", {})
        self.c_wolf = cfg.get("werewolf", {})
        self.c_react = cfg.get("reaction", {})
        self.c_contr = cfg.get("contrarian", {})
        self.c_emo = cfg.get("emotion", {})
        self.c_ally = cfg.get("ally_defense", {})
        self.c_reveal = cfg.get("reveal", {})
        self.c_history_window = cfg.get("history_window", 3)

    # ================================================================
    # PRIMARY ENTRY POINTS
    # ================================================================

    def compute_assertion(self, speaker_name: str) -> dict:
        """Returns {intent, target, emotion, engine_reasoning} for an unprompted assertion."""
        role = self.state.roles.get(speaker_name, "villager")
        dispatch = {
            "werewolf": self._werewolf_assertion,
            "guardian_angel": self._ga_assertion,
            "coroner": self._coroner_assertion,
        }
        return dispatch.get(role, self._villager_assertion)(speaker_name)

    def compute_reaction(self, reactor_name: str, speaker_name: str,
                         speaker_intent: str, speaker_target: str) -> dict:
        """Returns {intent, target, emotion, engine_reasoning, intensity} reacting to what was just said."""
        role = self.state.roles.get(reactor_name, "villager")
        if role == "werewolf":
            return self._werewolf_reaction(reactor_name, speaker_name, speaker_intent, speaker_target)
        return self._villager_reaction(reactor_name, speaker_name, speaker_intent, speaker_target)

    VOTE_REASONS = [
        "{target} has been evasive and suspicious all day.",
        "{target}'s behavior doesn't add up.",
        "The evidence points to {target}.",
        "{target} has been deflecting too much.",
        "I don't trust {target}'s story.",
    ]
    WOLF_VOTE_REASONS = [
        "{target} has been acting strangely.",
        "Something about {target} doesn't sit right with me.",
        "{target} hasn't given a straight answer all day.",
    ]

    def compute_vote(self, voter_name: str) -> dict:
        """Returns {target, thought_process} for voting phase."""
        role = self.state.roles.get(voter_name, "villager")

        if role == "werewolf":
            pack = [n for n, r in self.state.roles.items() if r == "werewolf" and n != voter_name]
            candidates = [n for n in self.state.alive_characters
                          if n != voter_name and n not in pack and n != "Player"]
            if not candidates:
                return {"target": "None", "thought_process": "No one left to vote for."}
            target = self._pick_weighted(candidates, self._get_suspicion_scores(voter_name, candidates, fake=True))
            reason = random.choice(self.WOLF_VOTE_REASONS).format(target=target)
            return {"target": target, "thought_process": reason}

        # Non-werewolf: vote for highest suspicion
        candidates = [n for n in self.state.alive_characters if n != voter_name and n != "Player"]
        if not candidates:
            return {"target": "None", "thought_process": "No one left to vote for."}
        target = self._pick_weighted(candidates, self._get_suspicion_scores(voter_name, candidates))
        reason = random.choice(self.VOTE_REASONS).format(target=target)
        return {"target": target, "thought_process": reason}

    def compute_kill_preference(self, werewolf_name: str, valid_targets: list) -> dict:
        """Returns {target, thought_process} for night kill."""
        if not valid_targets:
            return {"target": "None", "thought_process": "No targets."}

        # Prioritize: revealed roles (high value) > high intuition > high trust
        revealed_bonus = self.c_kill.get("revealed_role_bonus", 80)
        scores = {}
        for t in valid_targets:
            char = self.characters.get(t)
            if not char:
                scores[t] = self.c_kill.get("default_threat_score", 50)
                continue
            intuition_threat = char.intuition * self.c_kill.get("intuition_weight", 6)
            trust_threat = sum(
                self.state.trust_matrix.get(other, {}).get(t, 50)
                for other in self.state.alive_characters if other != t and other != werewolf_name
            ) / max(1, len(self.state.alive_characters) - 2)
            score = intuition_threat + trust_threat
            # Revealed GA/Coroner are high-value targets
            if t in self.state.revealed_roles:
                score += revealed_bonus
            scores[t] = score
        target = self._pick_weighted(valid_targets, scores)
        return {"target": target, "thought_process": f"{target} is too dangerous to leave alive."}

    def compute_protect_preference(self, ga_name: str, valid_targets: list) -> dict:
        """Returns {target, thought_process} for GA protection."""
        if not valid_targets:
            return {"target": "None", "thought_process": "No valid targets."}

        # Protect whoever seems most likely to be targeted: revealed roles > high intuition > high trust
        revealed_bonus = self.c_protect.get("revealed_role_bonus", 60)
        scores = {}
        for t in valid_targets:
            char = self.characters.get(t)
            trust_toward = self.state.trust_matrix.get(ga_name, {}).get(t, 50)
            iw = self.c_protect.get("intuition_weight", 5)
            default = self.c_protect.get("default_threat_level", 25)
            threat_level = (char.intuition * iw if char else default) + trust_toward
            # Revealed roles are prime wolf targets — prioritize protecting them
            if t in self.state.revealed_roles:
                threat_level += revealed_bonus
            scores[t] = threat_level
        target = self._pick_weighted(valid_targets, scores)
        return {"target": target, "thought_process": f"I must protect {target} tonight."}

    # ================================================================
    # SUSPICION UPDATES
    # ================================================================

    def update_all_suspicion(self, event_type: str, source: str, target: str, **ctx):
        """Updates suspicion for all observers after a public event."""
        for observer in self.state.alive_characters:
            if observer == source:
                continue
            self.update_suspicion(observer, source, target, event_type, **ctx)

    def update_suspicion(self, observer: str, source: str, target: str,
                         event_type: str, **ctx):
        """Updates suspicion_matrix[observer][source] based on a game event."""
        if observer not in self.state.suspicion_matrix:
            return
        if source not in self.state.suspicion_matrix[observer]:
            return

        char = self.characters.get(observer)
        int_div = self.c_sus.get("intuition_divisor", 5.0)
        lve_div = self.c_sus.get("logic_emotion_divisor", 5.0)
        intuition_mult = (char.intuition / int_div) if char else 1.0
        lve_mult = (char.logic_vs_emotion / lve_div) if char else 1.0

        delta = 0
        if event_type == "deflect_when_accused":
            lo, hi = self.c_sus.get("deflect_when_accused", [8, 15])
            delta = int(random.randint(lo, hi) * intuition_mult)
        elif event_type == "silence":
            lo, hi = self.c_sus.get("silence", [5, 10])
            delta = int(random.randint(lo, hi) * intuition_mult)
        elif event_type == "contradiction":
            lo, hi = self.c_sus.get("contradiction", [10, 20])
            delta = int(random.randint(lo, hi) * intuition_mult)
        elif event_type == "accused_cleared_innocent":
            lo, hi = self.c_sus.get("accused_cleared_innocent", [5, 12])
            delta = int(random.randint(lo, hi) * lve_mult)
        elif event_type == "defended_guilty":
            lo, hi = self.c_sus.get("defended_guilty", [10, 18])
            delta = int(random.randint(lo, hi) * lve_mult)
        elif event_type == "ally_defends":
            trust_to_defender = self.state.trust_matrix.get(observer, {}).get(ctx.get("defender", ""), 50)
            if trust_to_defender > TrustManager.TRUST_FRIENDLY_THRESHOLD:
                lo, hi = self.c_sus.get("ally_defends", [5, 10])
                delta = -random.randint(lo, hi)
        elif event_type == "coroner_clears":
            self.state.suspicion_matrix[observer][source] = 0
            return
        elif event_type == "ga_protected":
            lo, hi = self.c_sus.get("ga_protected", [10, 15])
            delta = -random.randint(lo, hi)

        if delta != 0:
            current = self.state.suspicion_matrix[observer].get(source, 0)
            self.state.suspicion_matrix[observer][source] = max(0, min(100, current + delta))

    def log_action(self, name: str, intent: str, target: str):
        """Records an action for contradiction detection."""
        if name not in self.state.contradiction_log:
            self.state.contradiction_log[name] = []
        self.state.contradiction_log[name].append((self.state.day, intent, target))

    # ================================================================
    # ROLE-SPECIFIC ASSERTION TREES
    # ================================================================

    def _villager_assertion(self, name: str) -> dict:
        # 1. Am I under attack?
        if self._is_under_attack(name):
            return self._build_result(name, "defend_self", "None")

        # 2. Is a trusted ally under attack?
        under_attack, ally = self._is_ally_under_attack(name)
        if under_attack and ally:
            return self._build_result(name, "defend_other", ally)

        # 3. Pick highest-suspicion target to accuse or question
        target = self._pick_suspicion_target(name)

        # 3b. Cold start: no suspicion data yet → use low trust as a proxy
        if not target:
            target = self._pick_low_trust_target(name)

        if target:
            char = self.characters.get(name)
            lve = char.logic_vs_emotion if char else 5
            ad = char.assertion_drive if char else 5

            ca = self.c_assert
            accuse_weight = ca.get("accuse_base_weight", 55) + (ca.get("accuse_low_logic_bonus", 15) if lve <= ca.get("low_logic_threshold", 4) else 0)
            question_weight = ca.get("question_base_weight", 30) + (ca.get("question_high_logic_bonus", 10) if lve >= ca.get("high_logic_threshold", 7) else 0)
            neutral_weight = max(ca.get("neutral_min_weight", 5), 100 - accuse_weight - question_weight)
            if ad <= ca.get("low_ad_threshold", 4):
                neutral_weight += ca.get("low_ad_neutral_bonus", 30)

            intent = random.choices(
                ["accuse", "question", "neutral"],
                weights=[accuse_weight, question_weight, neutral_weight],
                k=1
            )[0]
            return self._build_result(name, intent, target if intent != "neutral" else "None")

        # 4. Fallback: neutral
        return self._build_result(name, "neutral", "None")

    def _werewolf_assertion(self, name: str) -> dict:
        char = self.characters.get(name)
        performance = char.performance if char else 5
        pack = [n for n, r in self.state.roles.items() if r == "werewolf" and n != name]

        # 1. Is a packmate under heavy suspicion? Defend (gated by performance)
        for mate in pack:
            if mate in self.state.alive_characters and self._is_under_attack(mate):
                # Low performance wolves defend too obviously
                if random.random() < performance / self.c_wolf.get("packmate_defense_divisor", 10):
                    return self._build_result(name, "defend_other", mate)

        # 2. Am I under suspicion?
        if self._is_under_attack(name):
            if performance >= self.c_wolf.get("deflect_performance_threshold", 5):
                return self._build_result(name, "deflect", "None")
            else:
                return self._build_result(name, "defend_self", "None")

        # 3. Accuse an innocent (bandwagon strategy)
        target = self._werewolf_fake_suspicion(name)
        if target:
            return self._build_result(name, "accuse", target)

        # 4. Fallback: question someone to appear helpful
        innocents = [n for n in self.state.alive_characters
                     if n != name and n not in pack]
        if innocents:
            target = random.choice(innocents)
            return self._build_result(name, "question", target)

        return self._build_result(name, "neutral", "None")

    def _ga_assertion(self, name: str) -> dict:
        # GA acts like a villager but may reference protection knowledge
        if self._is_under_attack(name):
            return self._build_result(name, "defend_self", "None")

        under_attack, ally = self._is_ally_under_attack(name)
        if under_attack and ally:
            return self._build_result(name, "defend_other", ally)

        # If someone survived a night attack (GA protected), vouch for them
        if self.state.ga_protection_history:
            last_entry = self.state.ga_protection_history[-1]
            # Extract protected name
            for char_name in self.state.alive_characters:
                if char_name in last_entry and self._is_under_attack(char_name):
                    return self._build_result(name, "defend_other", char_name)

        # Fall through to villager logic
        return self._villager_assertion(name)

    def _coroner_assertion(self, name: str) -> dict:
        # Coroner acts like a villager but uses findings to drive accusations
        if self._is_under_attack(name):
            return self._build_result(name, "defend_self", "None")

        under_attack, ally = self._is_ally_under_attack(name)
        if under_attack and ally:
            return self._build_result(name, "defend_other", ally)

        # If coroner knows a confirmed wolf, find who defended them and accuse
        wolf_defender = self._find_wolf_defender(name)
        if wolf_defender:
            return self._build_result(name, "accuse", wolf_defender)

        return self._villager_assertion(name)

    # ================================================================
    # REACTION TREES
    # ================================================================

    def _villager_reaction(self, reactor_name: str, speaker_name: str,
                           speaker_intent: str, speaker_target: str) -> dict:
        trust_to_speaker = self.state.trust_matrix.get(reactor_name, {}).get(speaker_name, 50)
        trust_to_target = self.state.trust_matrix.get(reactor_name, {}).get(speaker_target, 50) if speaker_target != "None" else 50

        # 1. Am I being targeted?
        if speaker_target == reactor_name:
            if speaker_intent in ("accuse", "question"):
                return self._build_result(reactor_name, "defend_self", "None", intensity="high")
            elif speaker_intent == "defend_other":
                return self._build_result(reactor_name, "agree", speaker_name, intensity="medium")

        # 2. Is my trusted ally being attacked?
        if speaker_intent in ("accuse", "question") and speaker_target != "None":
            if trust_to_target >= TrustManager.TRUST_ALLIED_THRESHOLD:
                return self._build_result(reactor_name, "defend_other", speaker_target, intensity="high")
            elif trust_to_target >= TrustManager.TRUST_FRIENDLY_THRESHOLD:
                if random.random() < self.c_react.get("defend_other_friendly_chance", 0.6):
                    return self._build_result(reactor_name, "defend_other", speaker_target, intensity="medium")

        # 3. Is someone I suspect being defended?
        if speaker_intent == "defend_other" and speaker_target != "None":
            suspicion = self.state.suspicion_matrix.get(reactor_name, {}).get(speaker_target, 0)
            if suspicion > self.c_react.get("disagree_suspicion_threshold", 40):
                return self._build_result(reactor_name, "disagree", speaker_name, intensity="medium")

        # 4. Do I agree with an accusation/question? (trust speaker + distrust target)
        if speaker_intent in ("accuse", "question") and speaker_target != "None":
            if trust_to_speaker >= TrustManager.TRUST_FRIENDLY_THRESHOLD:
                suspicion = self.state.suspicion_matrix.get(reactor_name, {}).get(speaker_target, 0)
                if suspicion > self.c_react.get("agree_suspicion_threshold", 10):
                    return self._build_result(reactor_name, "agree", speaker_name, intensity="low")
                # Cold-start: no suspicion data yet, but low trust toward target = agree
                if trust_to_target < self.c_react.get("agree_cold_start_trust_threshold", 40):
                    if random.random() < self.c_react.get("agree_cold_start_chance", 0.4):
                        return self._build_result(reactor_name, "agree", speaker_name, intensity="low")

        # 5. Do I agree with a general statement? (high trust in speaker)
        if speaker_intent in ("disagree", "defend_other", "neutral") and trust_to_speaker >= self.c_react.get("agree_general_trust_threshold", 60):
            if random.random() < self.c_react.get("agree_general_chance", 0.25):
                return self._build_result(reactor_name, "agree", speaker_name, intensity="low")

        # 6. Contrarian roll
        if self._should_disagree(reactor_name, speaker_name):
            return self._build_result(reactor_name, "disagree", speaker_name, intensity="low")

        # 7. No meaningful reaction — skip this reactor
        return None

    def _werewolf_reaction(self, reactor_name: str, speaker_name: str,
                           speaker_intent: str, speaker_target: str) -> dict:
        char = self.characters.get(reactor_name)
        performance = char.performance if char else 5
        pack = [n for n, r in self.state.roles.items() if r == "werewolf" and n != reactor_name]

        # 1. Am I being accused?
        if speaker_target == reactor_name and speaker_intent in ("accuse", "question"):
            if performance >= self.c_wolf.get("reaction_deflect_threshold", 6):
                return self._build_result(reactor_name, "deflect", "None", intensity="high")
            else:
                return self._build_result(reactor_name, "defend_self", "None", intensity="high")

        # 2. Is a packmate being accused?
        if speaker_intent == "accuse" and speaker_target in pack:
            if random.random() < performance / self.c_wolf.get("reaction_packmate_defense_divisor", 12):
                return self._build_result(reactor_name, "defend_other", speaker_target, intensity="medium")

        # 3. Is an innocent being accused? Pile on (bandwagon)
        if speaker_intent == "accuse" and speaker_target not in pack and speaker_target != reactor_name:
            if random.random() < self.c_wolf.get("reaction_bandwagon_chance", 0.4):
                return self._build_result(reactor_name, "agree", speaker_name, intensity="low")

        # 4. Contrarian roll
        if self._should_disagree(reactor_name, speaker_name):
            return self._build_result(reactor_name, "disagree", speaker_name, intensity="low")

        # No meaningful reaction — skip this reactor
        return None

    # ================================================================
    # SHARED HELPERS
    # ================================================================

    def _build_result(self, name: str, intent: str, target: str, intensity: str = "medium") -> dict:
        """Packages a decision into the standard output format."""
        emotion = self._derive_emotion(name, intent)
        reasoning = self._generate_reasoning(intent, target)
        return {
            "intent": intent,
            "target": target if target else "None",
            "emotion": emotion,
            "engine_reasoning": reasoning,
            "intensity": intensity,
        }

    def _pick_suspicion_target(self, name: str) -> str | None:
        """Returns the character this person is most suspicious of, with weighted randomness."""
        suspicions = self.state.suspicion_matrix.get(name, {})
        threshold = self.c_assert.get("suspicion_target_threshold", 10)
        candidates = {k: v for k, v in suspicions.items()
                      if k in self.state.alive_characters and k != name and v > threshold}
        if not candidates:
            return None
        return self._pick_weighted(list(candidates.keys()), candidates)

    def _pick_low_trust_target(self, name: str) -> str | None:
        """Cold-start fallback: picks someone this character has low trust toward."""
        trusts = self.state.trust_matrix.get(name, {})
        candidates = {k: max(1, 100 - v) for k, v in trusts.items()
                      if k in self.state.alive_characters and k != name}
        if not candidates:
            return None
        # Only pick if at least one person has trust below neutral
        distrust_threshold = self.c_contr.get("trust_center", 50)
        if not any(trusts.get(k, 50) < distrust_threshold for k in candidates):
            char = self.characters.get(name)
            ad = char.assertion_drive if char else 5
            if random.random() > ad / self.c_contr.get("index_divisor", 10.0):
                return None
        return self._pick_weighted(list(candidates.keys()), candidates)

    def _pick_defense_target(self, name: str) -> str | None:
        """Returns the character this person most wants to defend (highest trust)."""
        trusts = self.state.trust_matrix.get(name, {})
        candidates = {k: v for k, v in trusts.items()
                      if k in self.state.alive_characters and k != name and v >= TrustManager.TRUST_FRIENDLY_THRESHOLD}
        if not candidates:
            return None
        return self._pick_weighted(list(candidates.keys()), candidates)

    def _should_disagree(self, reactor: str, speaker: str) -> bool:
        """Contrarian check: contrarian_index/10 chance, reduced by trust toward speaker."""
        char = self.characters.get(reactor)
        if not char:
            return False
        base_chance = char.contrarian_index / self.c_contr.get("index_divisor", 10.0)
        trust = self.state.trust_matrix.get(reactor, {}).get(speaker, 50)
        center = self.c_contr.get("trust_center", 50)
        divisor = self.c_contr.get("trust_divisor", 100)
        trust_modifier = max(0, (trust - center) / divisor)
        return random.random() < (base_chance - trust_modifier)

    def _derive_emotion(self, name: str, intent: str) -> str:
        """Maps intent → emotion, weighted by logic_vs_emotion stat."""
        char = self.characters.get(name)
        lve = char.logic_vs_emotion if char else 5
        low_pool, high_pool = EMOTION_MAP.get(intent, (["neutral"] * 10, ["neutral"] * 10))
        pool = low_pool if lve <= self.c_emo.get("logic_threshold", 5) else high_pool
        return random.choice(pool)

    def _generate_reasoning(self, intent: str, target: str) -> str:
        """Picks a template reasoning string."""
        templates = REASONING_TEMPLATES.get(intent, REASONING_TEMPLATES["neutral"])
        template = random.choice(templates)
        return template.format(target=target) if "{target}" in template else template

    def _is_under_attack(self, name: str) -> bool:
        """Check if name was accused in the last 3 logical_history entries."""
        recent = self.state.logical_history[-self.c_history_window:]
        for entry in recent:
            if f"[accuse] -> {name}" in entry or f"[question] -> {name}" in entry:
                return True
        return False

    def _is_ally_under_attack(self, name: str) -> tuple[bool, str | None]:
        """Check if someone this character trusts was recently accused.
        Allied threshold (75+): always defend. Friendly threshold (55+): probability roll."""
        trusts = self.state.trust_matrix.get(name, {})

        # First pass: guaranteed defend for allied (75+)
        for ally, score in trusts.items():
            if score >= TrustManager.TRUST_ALLIED_THRESHOLD and ally in self.state.alive_characters:
                if self._is_under_attack(ally):
                    return True, ally

        # Second pass: probabilistic defend for friendly (55+)
        for ally, score in trusts.items():
            if score >= TrustManager.TRUST_FRIENDLY_THRESHOLD and ally in self.state.alive_characters:
                if self._is_under_attack(ally):
                    # Higher trust = higher chance to defend
                    chance = (score - TrustManager.TRUST_FRIENDLY_THRESHOLD) / self.c_ally.get("friendly_probability_divisor", 40)
                    chance += self.c_ally.get("friendly_base_chance", 0.2)
                    if random.random() < chance:
                        return True, ally

        return False, None

    def _werewolf_fake_suspicion(self, wolf_name: str) -> str | None:
        """Pick an innocent to accuse. Prefers someone already somewhat suspected (bandwagon)."""
        pack = [n for n, r in self.state.roles.items() if r == "werewolf"]
        innocents = [n for n in self.state.alive_characters
                     if n != wolf_name and n not in pack]
        if not innocents:
            return None

        # Weight by how much suspicion others already have toward this target (bandwagon)
        scores = {}
        for target in innocents:
            total_suspicion = sum(
                self.state.suspicion_matrix.get(obs, {}).get(target, 0)
                for obs in self.state.alive_characters if obs != wolf_name
            )
            scores[target] = max(1, total_suspicion)
        return self._pick_weighted(innocents, scores)

    def _werewolf_should_fake_claim(self, wolf_name: str) -> tuple[bool, str]:
        """Performance-gated: decide if the wolf should fake-claim a role.
        Note: Superseded by _wolf_voluntary_reveal via check_reveal. Kept for reference."""
        char = self.characters.get(wolf_name)
        performance = char.performance if char else 5
        perf_threshold = self.c_wolf.get("voluntary_reveal_performance_threshold", 7)
        chance = self.c_wolf.get("voluntary_reveal_chance", 0.15)

        if performance < perf_threshold:
            return False, ""
        already_claimed = any(c["claimant"] == wolf_name for c in self.state.fake_claims)
        if already_claimed:
            return False, ""
        if random.random() > chance:
            return False, ""

        role = random.choice(["guardian_angel", "coroner"])
        return True, role

    def _get_suspicion_scores(self, voter: str, candidates: list, fake: bool = False) -> dict:
        """Gets suspicion scores for voting. Werewolves can fake them."""
        if fake:
            # Fake: high suspicion of innocents, low of pack
            pack = [n for n, r in self.state.roles.items() if r == "werewolf"]
            inno_w = self.c_wolf.get("fake_suspicion_innocent_weight", 80)
            wolf_w = self.c_wolf.get("fake_suspicion_wolf_weight", 5)
            return {c: (inno_w if c not in pack else wolf_w) for c in candidates}
        return {c: max(1, self.state.suspicion_matrix.get(voter, {}).get(c, 0)) for c in candidates}

    # ================================================================
    # FINDINGS & CLAIMS PROCESSING
    # ================================================================

    def _find_wolf_defender(self, name: str) -> str | None:
        """Finds an alive character who defended a confirmed werewolf. Used by coroner assertions."""
        confirmed_wolves = set()
        for finding in self.state.coroner_knowledge:
            if "werewolf" in finding:
                # Format: "Day X: NAME was werewolf"
                try:
                    wolf_name = finding.split(": ")[1].split(" was ")[0]
                    confirmed_wolves.add(wolf_name)
                except (IndexError, ValueError):
                    continue

        if not confirmed_wolves:
            return None

        # Search contradiction_log for defend_other actions targeting confirmed wolves
        defenders = []
        for char_name, actions in self.state.contradiction_log.items():
            if char_name not in self.state.alive_characters or char_name == name:
                continue
            for _day, intent, target in actions:
                if intent == "defend_other" and target in confirmed_wolves:
                    defenders.append(char_name)
                    break  # One match is enough per character

        if not defenders:
            return None
        return random.choice(defenders)

    def process_coroner_findings(self, finding: str):
        """Called when new coroner knowledge is added. Updates suspicion for wolf defenders."""
        if "werewolf" not in finding:
            return

        # Extract the confirmed wolf name
        try:
            wolf_name = finding.split(": ")[1].split(" was ")[0]
        except (IndexError, ValueError):
            return

        # Find everyone who defended the wolf and apply "defended_guilty" suspicion
        for char_name, actions in self.state.contradiction_log.items():
            if char_name not in self.state.alive_characters:
                continue
            for _day, intent, target in actions:
                if intent == "defend_other" and target == wolf_name:
                    self.update_all_suspicion(
                        "defended_guilty", source=char_name, target=wolf_name
                    )
                    break

    def process_duplicate_claim(self, claimant: str, claimed_role: str):
        """Called when someone reveals. If another person already claimed the same role,
        raises suspicion on BOTH claimants for all observers."""
        # Find existing claimants of the same role
        existing = [
            name for name, role in self.state.revealed_roles.items()
            if role == claimed_role and name != claimant
        ]
        if not existing:
            return

        lo, hi = self.c_sus.get("duplicate_claim", [15, 25])
        for observer in self.state.alive_characters:
            if observer == claimant:
                continue
            char = self.characters.get(observer)
            int_div = self.c_sus.get("intuition_divisor", 5.0)
            mult = (char.intuition / int_div) if char else 1.0
            delta = int(random.randint(lo, hi) * mult)

            # Raise suspicion on the new claimant
            if claimant in self.state.suspicion_matrix.get(observer, {}):
                current = self.state.suspicion_matrix[observer].get(claimant, 0)
                self.state.suspicion_matrix[observer][claimant] = min(100, current + delta)

            # Raise suspicion on existing claimants too
            for prev in existing:
                if observer == prev:
                    continue
                if prev in self.state.suspicion_matrix.get(observer, {}):
                    current = self.state.suspicion_matrix[observer].get(prev, 0)
                    self.state.suspicion_matrix[observer][prev] = min(100, current + delta)

    # ================================================================
    # ROLE REVEAL SYSTEM
    # ================================================================

    REVEAL_ROLE_LABELS = {
        "guardian_angel": "Guardian Angel",
        "coroner": "Coroner",
    }

    def check_all_reveals(self) -> list[tuple[str, dict]]:
        """Scans all alive NPCs for pending reveals. Called between assertion rounds.
        Returns a list of (name, reveal_result) tuples. At most one reveal per character."""
        reveals = []
        for name in self.state.alive_characters:
            if name == "Player" or name in self.state.revealed_roles:
                continue
            result = self._check_reveal(name)
            if result:
                reveals.append((name, result))
        return reveals

    def _check_reveal(self, name: str) -> dict | None:
        """Checks if a single character should reveal their role this round."""
        role = self.state.roles.get(name, "villager")

        # --- Pressure reveal: someone claimed my role ---
        if name in self.state.reveal_pressure:
            return self._pressure_reveal(name, role)

        # --- Voluntary reveal (GA/Coroner only) ---
        if role == "guardian_angel":
            return self._ga_voluntary_reveal(name)
        elif role == "coroner":
            return self._coroner_voluntary_reveal(name)

        # --- Voluntary werewolf fake reveal (under attack + high performance) ---
        if role == "werewolf":
            return self._wolf_voluntary_reveal(name)

        return None

    def _pressure_reveal(self, name: str, role: str) -> dict | None:
        """Someone claimed our role — decide whether to counter-reveal."""
        claimed_role = self.state.reveal_pressure.get(name)
        if not claimed_role:
            return None

        if role == "werewolf":
            return self._wolf_pressure_reveal(name)

        # Real role holder: high chance to counter-reveal (70-90%)
        char = self.characters.get(name)
        ad = char.assertion_drive if char else 5
        base = self.c_reveal.get("pressure_base_chance", 0.7)
        divisor = self.c_reveal.get("pressure_ad_divisor", 50)
        chance = base + (ad / divisor)
        if random.random() < chance:
            findings = self._get_findings_for_role(name, role)
            return self._build_reveal_result(name, role, findings, pressure=True)

        return None

    def _wolf_pressure_reveal(self, name: str) -> dict | None:
        """Wolf decides whether to counter-claim under pressure."""
        char = self.characters.get(name)
        performance = char.performance if char else 5
        claimed_role = self.state.reveal_pressure.get(name)

        perf_threshold = self.c_reveal.get("wolf_pressure_performance_threshold", 6)
        if performance < perf_threshold:
            return None

        if name in self.state.revealed_roles:
            return None

        chance = performance / self.c_reveal.get("wolf_pressure_chance_divisor", 15)
        if random.random() < chance:
            fake_role = claimed_role or random.choice(["guardian_angel", "coroner"])
            fake_findings = self._fabricate_findings(name, fake_role)
            result = self._build_reveal_result(name, fake_role, fake_findings, pressure=True)
            result["_fake_claim"] = {
                "claimant": name, "claimed_role": fake_role, "day": self.state.day
            }
            return result

        return None

    def _wolf_voluntary_reveal(self, name: str) -> dict | None:
        """High-performance wolf proactively fake-claims a role when under pressure."""
        char = self.characters.get(name)
        performance = char.performance if char else 5
        perf_threshold = self.c_wolf.get("voluntary_reveal_performance_threshold", 7)
        chance = self.c_wolf.get("voluntary_reveal_chance", 0.15)

        if performance < perf_threshold:
            return None
        if name in self.state.revealed_roles:
            return None
        if any(c["claimant"] == name for c in self.state.fake_claims):
            return None
        if not self._is_under_attack(name):
            return None
        if random.random() > chance:
            return None

        fake_role = random.choice(["guardian_angel", "coroner"])
        fake_findings = self._fabricate_findings(name, fake_role)
        result = self._build_reveal_result(name, fake_role, fake_findings, pressure=False)
        result["_fake_claim"] = {
            "claimant": name, "claimed_role": fake_role, "day": self.state.day
        }
        return result

    def _ga_voluntary_reveal(self, name: str) -> dict | None:
        """GA considers revealing voluntarily."""
        # Reveal if: under heavy attack AND has protection history to share
        if not self.state.ga_protection_history:
            return None
        if not self._is_under_attack(name):
            return None
        # Under attack + has info = good reason to reveal
        if random.random() < self.c_reveal.get("ga_voluntary_chance", 0.6):
            findings = list(self.state.ga_protection_history)
            return self._build_reveal_result(name, "guardian_angel", findings)
        return None

    def _coroner_voluntary_reveal(self, name: str) -> dict | None:
        """Coroner considers revealing voluntarily."""
        # Reveal if: has werewolf findings (critical info to share)
        if not self.state.coroner_knowledge:
            return None
        has_wolf_finding = any("werewolf" in f for f in self.state.coroner_knowledge)
        wolf_chance = self.c_reveal.get("coroner_wolf_finding_chance", 0.5)
        no_wolf_chance = self.c_reveal.get("coroner_no_wolf_chance", 0.15)
        chance = wolf_chance if has_wolf_finding else no_wolf_chance
        if self._is_under_attack(name):
            chance += self.c_reveal.get("coroner_under_attack_bonus", 0.3)
        if random.random() < chance:
            findings = list(self.state.coroner_knowledge)
            return self._build_reveal_result(name, "coroner", findings)
        return None

    def _build_reveal_result(self, name: str, claimed_role: str,
                              findings: list[str], pressure: bool = False) -> dict:
        """Packages a reveal action."""
        label = self.REVEAL_ROLE_LABELS.get(claimed_role, claimed_role)
        if pressure:
            reasoning = f"{name} is counter-claiming as the {label} to challenge the other claimant"
        else:
            reasoning = f"{name} is revealing as the {label} to share critical information"

        return {
            "intent": "reveal_role",
            "target": "None",
            "emotion": "arrogant" if not pressure else "angry",
            "engine_reasoning": reasoning,
            "intensity": "high",
            "claimed_role": claimed_role,
            "findings": findings,
        }

    def apply_reveal_pressure(self, claimant: str, claimed_role: str):
        """After someone reveals, pressure others who hold (or fake-hold) that role."""
        for name in self.state.alive_characters:
            if name == claimant:
                continue
            real_role = self.state.roles.get(name, "villager")
            # Pressure the real holder of that role
            if real_role == claimed_role:
                self.state.reveal_pressure[name] = claimed_role
            # Pressure wolves to counter-claim (performance-gated in the handler)
            elif real_role == "werewolf" and name not in self.state.revealed_roles:
                char = self.characters.get(name)
                if char and char.performance >= self.c_reveal.get("wolf_pressure_performance_threshold", 6):
                    self.state.reveal_pressure[name] = claimed_role

    def register_reveal(self, name: str, claimed_role: str):
        """Records a public role claim."""
        self.state.revealed_roles[name] = claimed_role

    def _get_findings_for_role(self, name: str, role: str) -> list[str]:
        """Gets the real findings for a role holder."""
        if role == "guardian_angel":
            return list(self.state.ga_protection_history)
        elif role == "coroner":
            return list(self.state.coroner_knowledge)
        return []

    def _fabricate_findings(self, wolf_name: str, fake_role: str) -> list[str]:
        """Werewolf invents plausible-sounding findings."""
        if fake_role == "guardian_angel":
            # Claim to have protected someone random
            others = [n for n in self.state.alive_characters if n != wolf_name]
            if others and self.state.day > 0:
                target = random.choice(others)
                return [f"Night {self.state.day - 1}: Protected {target}"]
            return []
        elif fake_role == "coroner":
            # Claim a lynched person was innocent (to cast doubt)
            pack = [n for n, r in self.state.roles.items() if r == "werewolf"]
            fake_findings = []
            for event in self.state.public_events:
                if "was lynched" in event:
                    # Extract name from "Day X Voting: NAME was lynched"
                    try:
                        lynched = event.split(": ")[1].split(" was lynched")[0]
                        # Wolves lie: claim packmates were innocent, innocents were wolves
                        if lynched in pack:
                            fake_findings.append(f"{lynched} was innocent")
                        else:
                            fake_findings.append(f"{lynched} was innocent")
                    except (IndexError, ValueError):
                        continue
            return fake_findings
        return []

    @staticmethod
    def _pick_weighted(candidates: list, scores: dict) -> str:
        """Weighted random choice. Higher score = more likely to be picked."""
        weights = [max(1, scores.get(c, 1)) for c in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]
