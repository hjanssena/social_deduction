import json
import random

import pytest

from core.game_master import GameMaster
from core.io_handler import IOHandler
from models.character import Character
from models.characters_data import RAW_CHARACTER_DATA
from services.prompt_service import PromptService


class FakeLLM:
    """Scripted LLM: returns queued answers in order and records every prompt it receives."""

    def __init__(self):
        self.json_answers = []
        self.text_answers = []
        self.calls = []  # [(kind, system, prompt)]

    def generate_json(self, system_prompt, user_prompt, *args, **kwargs):
        self.calls.append(("json", system_prompt, user_prompt))
        return self.json_answers.pop(0) if self.json_answers else {}

    def generate_text(self, system_prompt, user_prompt, *args, **kwargs):
        self.calls.append(("text", system_prompt, user_prompt))
        return self.text_answers.pop(0) if self.text_answers else ""

    @property
    def last_prompt(self):
        return self.calls[-1][2]


class RecordingIO(IOHandler):
    """Captures output instead of printing; answers prompts from a queue (default: Enter / first option)."""

    def __init__(self):
        super().__init__()
        self.lines = []
        self.inputs = []

    def display(self, text):
        self.lines.append(text)

    def prompt(self, text=""):
        return self.inputs.pop(0) if self.inputs else ""

    def pause(self, text=""):
        pass

    def prompt_menu(self, title, options, context=""):
        self.lines.append(title)
        answer = self.inputs.pop(0) if self.inputs else "1"
        return int(answer) - 1


@pytest.fixture
def config():
    with open("config.json") as f:
        cfg = json.load(f)
    cfg.setdefault("debug", {})["dump_logbooks"] = False
    return cfg


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def io():
    return RecordingIO()


@pytest.fixture
def make_gm(config, llm, io):
    """Builds a GameMaster with a fixed seed so roles and logbooks are reproducible."""
    def build(seed=5):
        random.seed(seed)
        chars = [Character(f"npc_{c['name'].lower()}", c) for c in RAW_CHARACTER_DATA]
        return GameMaster(llm, PromptService(), chars, config, io=io)
    return build


@pytest.fixture
def gm(make_gm):
    return make_gm()
