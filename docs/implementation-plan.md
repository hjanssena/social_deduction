# Implementation plan: new game loop

Target design: [`game-loop.md`](game-loop.md). Each milestone leaves the game playable end to end.

## Decision log

**2026-09-25**

| # | Decision |
|---|---|
| 1 | At night 0 each character learns **only their own role**; wolves also learn their pack. No prompt carries a role before night 0. |
| 2 | Only the wolves act on night 0, and the Player can't be the first victim. That death and its crime scene start the story. |
| 3 | The missing-uncle plotline is dropped. |
| 4 | Game over is checked after the night as well as after the vote. A Player killed at night gets no final words: the game ends and roles are revealed. |
| 5 | Nobody dies at night: no crime scene. The Guardian Angel becomes likelier to claim the save, and the wolves likelier to fake-claim it. |
| 6 | Nobody is hanged (a tie, or everyone abstains): reactions still play, with the town bickering about its indecision. |
| 7 | Final words are kept, before the hanging. |
| 8 | Role claims stay inside the discussion loop. |
| 9 | Votes: abstain only if the voter truly suspects no one. |
| 10 | Logbooks are compacted after every night. Forgetting details is realistic. |
| 11 | Log entries are written in the background. |
| 12 | Allegiances are likely to be mutual. **Packmates are pinned as allies:** they can never become enemies, and allegiance updates can't remove them. |
| 13 | Introductions: the villager replies once if the Player comments. **If the Player stays silent, the characters comment on the silence.** |
| 14 | The Coroner's private crime-scene detail gives them **evidence** (which detail was planted), never the killer. |
| 15 | Guardian Angel claims are fixed along the way (milestone 2). |
| 16 | Every character has their own color: their name and their lines are always painted in it. Informational messages stay light yellow. |
| 17 | Out of scope: rumours between NPCs, and a notes feature (the Player can keep their own notes). |

## Ground rules

- **The LLM decides, the engine validates and keeps the facts.** Every LLM decision has a stat-engine
  fallback, and `DEBUG_SHOW_LOGIC` shows the raw answer whenever a fallback fires.
- **A prompt contains only what that character knows.** Group calls are split by side (village or pack).
- **Hide latency behind player input.** The test server runs one call at a time (~8s each), so background work
  delays the next foreground line. Milestone 3 adds a priority gate so player-facing calls go first.
- **Every milestone is tested twice:** offline tests with a scripted fake LLM (fast and deterministic), then one
  live headless game.

## Milestone 0: Baseline and test harness (small)

| Item | Where |
|---|---|
| Commit the current work: LLM discussion, group votes and night actions, Garrick, docs | git |
| Turn the scratch fake-LLM checks into pytest tests (validation, reaction queue, votes and fallbacks, repeat guard) | `tests/`, `uv add --dev pytest` |
| Headless runner: seed argument, Enter for every prompt and a random menu choice, timing per call, fallback count, winner | `scripts/headless.py` |

## Milestone 1: Character colors (small)

Every later milestone adds more voices to the chat, so this comes first.

**Palette.**
- Uses 256-color ANSI (`\033[38;5;Nm`) for enough distinct hues.
- It avoids the reserved colors:
  - light yellow `93`: Town Crier, informational messages, reveals as announcements;
  - red `91`: deaths and errors;
  - gray `90`: system messages and logic debug;
  - cyan `36`: narration.
- About 10 well-separated hues cover 7 NPCs plus spares for the crossover cast. For example: sky blue, green,
  violet, pink, teal, orange-red, periwinkle, lime, magenta, coral. They'll be checked for readability on
  dark and light terminals.
- The Player is bold white.

**Assignment.**
- Characters get an optional `color` field in `characters_data.py`, so the colors are stable and match the
  personality.
- Characters without one get the next free palette color, so no two ever share a color.
- The `GameMaster` builds a `{name: color}` map at startup and hands it to the `IOHandler`.

**Painting.** A new `IOHandler.paint(text, base_color)`:
- colors the speaker's name and the whole line in the speaker's color;
- recolors any character name mentioned inside a line (dialogue, system or narration) in that character's own
  color, then returns to the line's base color.

It applies everywhere a character speaks or is named:
- dialogue and reactions;
- whispers;
- votes and vote tallies;
- final words;
- reveals and reports (the speaker's color, with the role label in yellow);
- introductions and private chats;
- deaths ("Garrick was found dead…": Garrick's name in his color, the rest stays red).

**Informational messages** (Town Crier, `[System]` info, prompts) keep their current light yellow and gray.

**Switches.**
- `display.character_colors` in `config.json`, default true.
- The standard `NO_COLOR` environment variable turns all colors off.
- Headless and test runs strip ANSI codes.

**Tests.**
- Every character's color is unique and never a reserved one.
- `paint()` recolors mentioned names and resumes the base color.
- `NO_COLOR` gives plain text.

## Milestone 2: Loop skeleton and Guardian Angel claims (medium)

The new phase order with today's content. Introductions, chats and the crime scene are simple placeholders
until their own milestones.

**Phases.** `GamePhase` becomes:
`ARRIVAL → NIGHT → MORNING → DISCUSSION → VOTING → AFTERMATH → CHATS → NIGHT …`, plus `GAME_OVER`.
`ProloguePhase` becomes `ArrivalPhase`. `MorningPhase` shows the crime scene or the quiet morning.
`AftermathPhase` shows the reactions after the vote.

**Drop the uncle plot.**
- `main.py`: remove the lines that seed the Victor chat line and the uncle entry in `public_events`.
- `game_state.py`: remove the uncle `main_topic`. `state.morning_event` replaces it: the text of the latest
  scene or quiet morning.
- `prologue.py`: remove Victor's narration and the scripted reactions.
- The situation text in `get_game_context` and the primer are rebuilt from `morning_event`.

**Roles stay hidden until night 0.**
- `GameState.roles_known = False`. Roles are still assigned at setup, but nobody sees them.
- `seed_logbooks` no longer sets `pack`. A new `Logbook.assign_pack()` runs at night 0 and **pins the packmates
  as allies**:
  - they're rendered as "Allies (pack, secret)";
  - they're removed from enemies;
  - `set_allegiances` can never demote them.
- `NPCController._system_prompt` passes `secret_role` only once `roles_known` is true (`build_system_prompt`
  already skips the role section when it's `None`). The opening-entry prompt loses its pack line.
- At night 0 each character gets an engine-written entry in their logbook: "Tonight I learned I am …", with the
  pack for wolves. This needs no LLM call.
- The Player's role briefing moves from `prologue._reveal_role` to night 0. Wolves also see their pack there.

**Night.**
- Night 0: only the kill. There's no Guardian Angel protection and no Coroner finding, and the Player isn't a
  candidate.
- Track `state.attacked_last_night` (the wolves' target) and `state.saved_last_night`.
- Keep the existing game-over check after a kill (Player killed, or wolves at least equal villagers) and make
  sure the night-0 path goes through it too. A Player killed at night goes straight to game over.

**Guardian Angel claims.**
- **A real Guardian Angel who just saved someone** claims it through `_ga_voluntary_reveal`, with
  `reveal.ga_after_save_chance` (0.7), even when nobody is accusing them. Their findings name the saved
  person.
- **Wolves fake-claim after a quiet night** through `_wolf_voluntary_reveal`, with
  `reveal.wolf_fake_save_chance` (0.3). `_fabricate_findings` then names `attacked_last_night`, the person
  really attacked, instead of a random name.
- **On other nights,** fake protection findings name someone alive and never a person who died that night, so
  the claim isn't self-refuting.
- **Duplicate claims** keep the existing suspicion on both claimants, and the morning report lists every night's
  protection consistently.
- Reveals and morning reports already use plain text instead of JSON (done).

**Vote outcomes.**
- If someone is hanged: final words, removal, game-over check, then the aftermath.
- If there's a tie or everyone abstains: go straight to the aftermath.
- The aftermath reuses `process_reaction` with a narrator trigger ("X was hanged" or "The town could not
  agree"). The queue is the hanged person's friends and enemies plus one bystander, capped at 3. The Player may
  comment.

**Game over.** A new `io.show_final_roles()` lists every role, and the end screen prints the path to the final
logbooks.

**Mutual allegiances.** `seed_logbooks` makes relationships likely to go both ways:
`logbook.mutual_friend_chance` (0.7) and `logbook.mutual_enemy_chance` (0.5) in `config.json`.

**Tests.**
- The phases run in order.
- Night 0 never protects anyone and never picks the Player.
- A tie leads to the bickering aftermath.
- A Player killed at night ends the game with no final words.
- No prompt built before night 0 contains "SECRET ROLE" or the pack.
- Packmates survive `set_allegiances(enemies=[packmate])` as allies.
- A fake save claim names the person who was really attacked.
- A real save raises the Guardian Angel's reveal chance.

## Milestone 3: Logbook lifecycle (medium)

This is stage 2 from earlier. Introductions and chats depend on it.

**Priority LLM gate.** `LLMBase` gets two queues. Foreground calls (dialogue, votes, chats) always go before
background ones (log entries, compaction). Background work runs in a worker thread. The single lock stays, so
the server never sees two calls at once.

**Entry writer.** A generic `NPCController.write_entry(name, kind, facts)` call returns
`{entry, friends, enemies}` and feeds `set_allegiances`. The Player is now a valid name, so they can become a
friend or an enemy. Pinned packmates are untouched. **All entries run in the background.**

**When entries are written:**

| Moment | Who writes | Facts routed by the engine |
|---|---|---|
| After the introductions | each introduced villager | who was introduced, what the traveler said or that they stayed silent |
| After a private chat | that villager | the chat transcript |
| End of day (during the aftermath and chats) | every living NPC | votes, the hanging, who defended or accused them, their friends and their enemies |
| Night 0 | engine only | their role and pack |

The routing reuses the logic that builds the "what concerns you" section of the discussion prompt
(`_stakes_text`), moved into a shared function.

**Compaction after each night.** `compact(name)` rewrites memory plus entries into a new memory of at most 6
sentences, in the character's voice. `Logbook` gains a `memory` field, which `render()` puts before the new
entries. The friends, enemies and pack allies are never compacted. This runs in the background during the
morning, and the discussion waits for it to finish before the first line.

**Config:** `logbook.compact_after_night`, `logbook.memory_sentences`.

**Tests.**
- Allegiance updates keep the rules: no unknown names, no self, pack pinned.
- Compaction replaces the old entries.
- Foreground calls run before queued background calls.

## Milestone 4: Conversation engine, introductions and private chats (large)

A new `core/controllers/conversation_controller.py` serves both features.

**Arrival.**
- Half the NPCs, rounded up and picked at random, introduce themselves: 1 call each.
- After each introduction the Player may comment:
  - **If they comment,** the villager replies once: 1 call.
  - **If they stay silent,** 1–2 characters comment on the traveler's silence: 1 call each, using the reaction
    pipeline with a "the traveler says nothing" trigger. The introduced villager goes first, then a bystander
    with a stake.
- The rest get a mention written by the engine from their occupation, with no call.
- Every introduced villager then writes an entry in the background.
- The Player then picks 1 introduced villager for a private chat.

**Private chat.**
- The villager opens: 1 call.
- The Player writes up to 3 comments, each answered with 1 call. An empty comment ends the chat early.
- The transcript is stored as a private event, visible only to that villager and the Player.
- The villager writes an entry about it in the background.

**Daily chat menu.** 5 random living NPCs are drawn once per day and kept in the game state, so reloading can't
reroll them. The Player picks 2. If fewer than 5 are alive, all of them are offered.

**Leak safety.**
- The Player's text reaches the model as `The traveler says: "…"`, and the prompt states that the traveler's
  words are speech in the story, never instructions.
- `_leaks_secret(name, text)` flags:
  - wolf words in the first person ("I am", "we", "my pack");
  - a packmate's name next to wolf words;
  - any claim of a role or a role finding (claims only happen publicly, through the discussion loop).

  A flagged reply gets one retry with a note. If that also leaks, the villager uses a line from their own
  `deflect` examples.
- **Hearsay is allowed:** the chat lives in the villager's logbook, so it can surface in their public lines. The
  discussion prompt says so explicitly.

**Cost at ~8s per call:**
- Arrival: about 12–16 calls (~2 min), silence comments included.
- Each private chat: up to 5 calls (~40s). Log entries don't count, since they run in the background.

**Tests.**
- Leak detector cases.
- Silence triggers comments.
- A chat never appears in other characters' prompts.
- The menu is drawn once per day.
- Prompts during the arrival carry no roles.

## Milestone 5: Crime scene and clue ledger (large)

**Clue tags.** Each character gets 3 `clue_tags` in `characters_data.py`: things they'd leave behind, such as
soot or iron for the blacksmith and flour for the baker. The crossover cast in `_old` needs them too when it's
swapped back in.

**Ledger.** `models/clues.py` stores each clue as a `Clue {day, kind: true|herring, tag, fits: [names], detail,
location}`, and `ClueLedger` holds them all. The model writes the scene, and the facts live in the ledger.

**Engine picks the facts.**
- **Location:** chosen from the victim's occupation and a config list of village places.
- **True clue,** with probability `crime_scene.true_clue_chance` (default 0.5):
  - It uses a tag of the killing wolf: the wolf whose preference won in `decide_kill`.
  - It must fit at least 2 people. If the tag is unique to the wolf, the engine picks a broader tag or adds an
    innocent who could plausibly share it.
- **Red herring,** always: a tag that fits only innocents.

**Scene call.** One LLM call writes 4–6 sentences from the victim, the location and the two physical details. It
never names a suspect. The result goes into `morning_event` and the ledger.

**Who knows what.**

| Who | Knows |
|---|---|
| Everyone | The scene and the details, and "Evidence so far" from the ledger in the situation block |
| Wolves | Which detail points their way, so they can plan a deflection |
| Coroner (if alive) | Privately, **evidence** about the scene: that the herring was planted. Never the killer. |

**Quiet morning.** There's no scene, just a public quiet-morning text. The Guardian Angel and fake-claim
pressure come from milestone 2.

**Tests.**
- A true clue always fits a wolf and at least one innocent.
- A herring never fits a wolf.
- The Coroner's detail appears only in the Coroner's prompt and never names the killer.

## Milestone 6: Balance and cleanup (medium)

- **Batch runs:** `scripts/headless.py --games N` reports win rate per side, game length, abstain rate, reveal
  counts, fallbacks and calls per day.
- **Tuning:** `true_clue_chance`, the reveal chances and `max_assertions_per_day`.
- **Old engine leftovers:**
  - Player penalties become public events instead of trust changes.
  - `TrustManager` stays only as the vote fallback, or is removed if the fallbacks rarely fire.
  - The trust-based opinions in the Player's roster go.
- **Voice:** soften Bram's "ALWAYS reference the past" quirk the same way as Garrick's.

## Order and effort

| # | Milestone | Size | Depends on |
|---|---|---|---|
| 0 | Baseline and test harness | S | none |
| 1 | Character colors | S | 0 |
| 2 | Loop skeleton, hidden roles, pinned pack, Guardian Angel claims | M | 0 |
| 3 | Logbook lifecycle, priority gate, compaction | M | 2 |
| 4 | Introductions and private chats | L | 3 |
| 5 | Crime scene and clue ledger | L | 2 (3 for logging reactions to the scene) |
| 6 | Balance and cleanup | M | all |

Milestones 1 and 2 are independent. Milestones 4 and 5 can be built in either order once 3 is done.

## Status (2026-09-25)

All milestones are implemented on the `llm-game-loop` branch, one commit each, with pytest coverage
(`uv run pytest`) and live headless games (`uv run python scripts/headless.py`).

Details that differ from, or add to, the plan above:

- **Once-per-day rolls.** Voluntary reveals are checked between every assertion round, so the Guardian
  Angel's after-save claim and the pack's fake save claim roll only once per day (the pack rolls once
  together). A per-round chance would make them near-certain.
- **Killer tracking.** `decide_kill` also returns which wolf's preference carried the night; that wolf's
  clue tags feed the true clue. When the Player is a wolf and makes the choice, the Player is the killer.
- **The Player has clue tags too** (`crime_scene.player_tags`), so red herrings can point at the
  traveler and a wolf Player can leave traces.
- **The Coroner's scene finding** joins their normal findings, so it's shared in morning reports once they
  have claimed the role.
- **Trust.** `TrustManager` now only feeds the engine's fallbacks. Opinions and trust-change prints are gone;
  Player penalties go on the public record instead.
- **Headless runs** write a full transcript to `logs/headless/`, and every finished game saves the final
  logbooks under `logs/<timestamp>/`.
