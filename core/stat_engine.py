import random
from core.trust_manager import TrustManager



class StatEngine:
    """Deterministic + weighted-random engine for votes, night actions and role reveals.
    Discussion (assertions and reactions) is decided by the LLM in NPCController."""

    def __init__(self, game_state, characters: dict, config: dict = None):
        self.state = game_state
        self.characters = characters
        cfg = config or {}
        self.c_sus = cfg.get("suspicion", {})
        self.c_kill = cfg.get("kill", {})
        self.c_protect = cfg.get("protect", {})
        self.c_wolf = cfg.get("werewolf", {})
        self.c_reveal = cfg.get("reveal", {})
        self.c_history_window = cfg.get("history_window", 3)
        self._rolled = set()  # Keys of once-per-day chances that were already rolled

    def _first_roll(self, *key) -> bool:
        """True the first time `key` is seen: turns a per-round check into a single roll."""
        if key in self._rolled:
            return False
        self._rolled.add(key)
        return True

    # ================================================================
    # VOTES & NIGHT ACTIONS
    # ================================================================

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
    # SHARED HELPERS
    # ================================================================

    def _is_under_attack(self, name: str) -> bool:
        """Check if name was accused in the last 3 logical_history entries."""
        recent = self.state.logical_history[-self.c_history_window:]
        for entry in recent:
            if f"[accuse] -> {name}" in entry or f"[question] -> {name}" in entry:
                return True
        return False

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
        wolves = {n for n, r in self.state.roles.items() if r == "werewolf"}
        # Roles the pack already claims (publicly or in this scan): a second wolf claim would out both
        pack_claims = {role for n, role in self.state.revealed_roles.items() if n in wolves}
        for name in self.state.alive_characters:
            if name == "Player" or name in self.state.revealed_roles:
                continue
            result = self._check_reveal(name)
            if not result:
                continue
            if name in wolves:
                if result["claimed_role"] in pack_claims:
                    continue
                pack_claims.add(result["claimed_role"])
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
        """After a quiet night the pack may fake-claim the save (one roll per day for the whole pack).
        Otherwise a high-performance wolf may fake-claim a role when under pressure."""
        if (self.state.saved_last_night and not self.state.fake_claims_on(self.state.day)
                and self._first_roll("wolf_fake_save", self.state.day)
                and random.random() < self.c_reveal.get("wolf_fake_save_chance", 0.3)):
            result = self._build_reveal_result(name, "guardian_angel",
                                               self._fabricate_findings(name, "guardian_angel"), pressure=False)
            result["_fake_claim"] = {"claimant": name, "claimed_role": "guardian_angel", "day": self.state.day}
            return result

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
        # The morning after a save: one roll to claim it, even when nobody is accusing them
        if (self.state.saved_last_night and self._first_roll("ga_save", name, self.state.day)
                and random.random() < self.c_reveal.get("ga_after_save_chance", 0.7)):
            return self._build_reveal_result(name, "guardian_angel", list(self.state.ga_protection_history))

        # Otherwise reveal if: under heavy attack AND has protection history to share
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
            # Pressure wolves to counter-claim (performance-gated in the handler),
            # never over a packmate's own claim
            elif (real_role == "werewolf" and name not in self.state.revealed_roles
                  and self.state.roles.get(claimant) != "werewolf"):
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
            if self.state.day <= 1:
                return []  # Nobody protected anyone on night 0
            night = f"Night {self.state.day - 1}"
            # After a quiet night, claim the save of the person the pack really attacked
            if self.state.saved_last_night and self.state.attacked_last_night:
                return [f"{night}: Protected {self.state.attacked_last_night} "
                        f"(nobody died, so I must have stopped the wolves)"]
            # Otherwise someone alive (the dead can't have been protected)
            others = [n for n in self.state.alive_characters if n != wolf_name]
            return [f"{night}: Protected {random.choice(others)}"] if others else []
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
