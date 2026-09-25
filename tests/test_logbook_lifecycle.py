"""Logbook lifecycle: background entries, allegiance updates, nightly compaction, priority gate."""
import threading
import time

from core.background import BackgroundWorker
from services.llm_base import BACKGROUND, LLMBase


def npcs(gm):
    return [n for n in gm.state.alive_characters if n != "Player"]


def test_entry_is_written_and_allegiances_follow_the_rules(gm, llm):
    wolves = [n for n, r in gm.state.roles.items() if r == "werewolf"]
    wolf = next(w for w in wolves if w != "Player")
    book = gm.state.logbooks[wolf]
    book.assign_pack(wolves)
    mate = next(w for w in wolves if w != wolf)
    llm.json_answers = [{"entry": "The traveler kept quiet. Good.", "friends": ["player"], "enemies": [mate]}]
    gm.npc_controller.write_entry(wolf, "End of day", ["Something happened."])
    assert book.entries[-1]["text"] == "The traveler kept quiet. Good."
    assert "Player" in book.friends
    assert mate not in book.enemies and mate in book.pack


def test_entry_without_lists_keeps_allegiances(gm, llm):
    name = npcs(gm)[0]
    book = gm.state.logbooks[name]
    before = (list(book.friends), list(book.enemies))
    llm.json_answers = [{"entry": "A long day."}]
    gm.npc_controller.write_entry(name, "End of day", ["x"])
    assert (book.friends, book.enemies) == before


def test_compaction_folds_entries_into_memory(gm, llm):
    name = npcs(gm)[0]
    book = gm.state.logbooks[name]
    book.add_entry(1, "Morning", "Saw blood on the mill.")
    llm.text_answers = ["I remember blood on the mill wheel."]
    gm.npc_controller.compact_logbook(name)
    assert book.entries == [] and book.memory == "I remember blood on the mill wheel."
    assert "Memories: I remember blood" in book.render()
    assert book.friends or book.enemies  # The table survives compaction


def test_day_facts_route_votes_through_the_allegiance_table(gm):
    st = gm.state
    name = npcs(gm)[0]
    book = st.logbooks[name]
    friend = book.friends[0]
    voter = next(n for n in npcs(gm) if n not in (name, friend))
    st.votes_by_day[st.day] = {name: voter, voter: friend, friend: name}
    facts = gm.npc_controller.day_facts(name)
    assert f"You voted to hang {voter}." in facts
    assert f"{friend} voted to hang you." in facts
    assert f"{voter} voted to hang your friend {friend}." in facts


def test_background_worker_marks_its_thread_and_waits():
    seen = []
    worker = BackgroundWorker()
    worker.submit(lambda: seen.append(getattr(BACKGROUND, "active", False)))
    worker.wait_idle()
    assert seen == [True] and worker.pending() == 0


class SlowLLM(LLMBase):
    def __init__(self):
        super().__init__({})
        self.order = []

    def _chat(self, system_prompt, user_prompt, cfg, json_mode=False):
        time.sleep(0.05)
        self.order.append(user_prompt)
        return "ok"


def test_priority_gate_serves_foreground_first():
    llm = SlowLLM()
    worker = BackgroundWorker()
    first = threading.Thread(target=llm.generate_text, args=("s", "first"))
    first.start()
    time.sleep(0.01)  # "first" now holds the gate
    worker.submit(llm.generate_text, "s", "background")
    time.sleep(0.01)
    fg = threading.Thread(target=llm.generate_text, args=("s", "foreground"))
    fg.start()
    first.join(); fg.join(); worker.wait_idle()
    assert llm.order == ["first", "foreground", "background"]
