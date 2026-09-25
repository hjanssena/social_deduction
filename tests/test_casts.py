"""Both casts carry everything the game uses, and the setting picks one."""
import re

import pytest

from core.colors import RESERVED_256
from models.characters_data import CASTS, CROSSOVER, load_cast

FIELDS = ("name", "clue_tags", "color", "occupation", "bio", "archetype", "speech_pattern", "verbal_quirks",
          "stats", "speech_examples")
INTENTS = ("accuse", "defend_other", "defend_self", "agree", "disagree", "question", "deflect", "neutral")


@pytest.mark.parametrize("cast_name", list(CASTS))
def test_every_profile_is_complete(cast_name):
    cast = CASTS[cast_name]
    assert len(cast) == 7
    for c in cast:
        assert all(c.get(f) for f in FIELDS), c["name"]
        assert set(c["speech_examples"]) >= set(INTENTS), c["name"]
        assert len(c["stats"]) == 6


@pytest.mark.parametrize("cast_name", list(CASTS))
def test_colors_are_unique_and_never_a_message_color(cast_name):
    colors = [c["color"] for c in CASTS[cast_name]]
    assert len(set(colors)) == len(colors) and not set(colors) & RESERVED_256


@pytest.mark.parametrize("cast_name", list(CASTS))
def test_everyone_shares_a_trace_with_someone(cast_name):
    """A true clue must fit the killer and an innocent, so every character needs a shared clue tag."""
    cast = CASTS[cast_name]
    for c in cast:
        others = {t for o in cast if o is not c for t in o["clue_tags"]}
        assert set(c["clue_tags"]) & others, c["name"]


def test_crossover_profiles_carry_no_dropped_plotlines():
    text = str(CROSSOVER).lower()
    assert not re.search(r"\buncle\b", text) and "prologue_reactions" not in text
    assert all("examples:" in c["verbal_quirks"].lower() and len(c["verbal_quirks"]) > 150 for c in CROSSOVER)


def test_the_setting_picks_the_cast():
    assert load_cast({}) is CROSSOVER
    assert load_cast({"setup": {"cast": "village"}}) is CASTS["village"]
    with pytest.raises(ValueError):
        load_cast({"setup": {"cast": "nope"}})


def test_parser_examples_use_names_from_the_current_cast(gm):
    from services.prompt_service import PromptService
    examples = PromptService._parser_examples(gm.get_roster_text(viewer="Player"))
    first = [n for n in gm.state.alive_characters if n != "Player"][0]
    assert f'"target": "{first}"' in examples and "Elara" not in examples
