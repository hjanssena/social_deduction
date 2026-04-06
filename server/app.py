"""FastAPI game server — wraps the existing engine with an HTTP event-queue API.

The game engine runs in a background thread.  The ServerIOHandler bridges
engine ↔ HTTP by pushing typed events onto a queue (consumed by GET /game/next)
and blocking on a response queue (fed by POST /game/respond).

Endpoints:
    POST /game/start   — initialize and start a new game
    GET  /game/next    — long-poll for the next event
    POST /game/respond — send player input (text, menu index, or empty for pause)
    GET  /game/state   — snapshot of current game state
"""

import json
import queue
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from server.io_adapter import ServerIOHandler
from services.llm_factory import create_llm
from services.prompt_service import PromptService
from models.character import Character
from models.characters_data import RAW_CHARACTER_DATA
from core.game_master import GameMaster

app = FastAPI(title="Social Deduction Game Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Game state (single game at a time)
# ------------------------------------------------------------------

_game_lock = threading.Lock()
_gm: GameMaster | None = None
_io: ServerIOHandler | None = None
_engine_thread: threading.Thread | None = None


def _run_engine():
    """Entry point for the background engine thread."""
    global _gm
    _gm.state.public_events.append(
        "Last night, Victor's uncle mysteriously disappeared without a trace. Victor is the town Mayor."
    )
    _gm.state.chat_history.append(
        "[Victor (Mayor)]: 'Quiet down! My uncle has vanished...'"
    )
    _gm.run_loop()


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------

class RespondBody(BaseModel):
    value: str = ""


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.post("/game/start")
def start_game():
    global _gm, _io, _engine_thread

    with _game_lock:
        with open("config.json", "r") as f:
            config = json.load(f)

        llm = create_llm(config)
        prompt_builder = PromptService()
        characters = [Character(f"npc_{c['name'].lower()}", c) for c in RAW_CHARACTER_DATA]

        _io = ServerIOHandler()
        _gm = GameMaster(
            llm_service=llm,
            prompt_service=prompt_builder,
            characters=characters,
            config=config,
            io=_io,
        )

        _engine_thread = threading.Thread(target=_run_engine, daemon=True)
        _engine_thread.start()

    return {
        "status": "started",
        "characters": [c["name"] for c in RAW_CHARACTER_DATA],
        "alive": list(_gm.state.alive_characters),
        "roles": {k: v for k, v in _gm.state.roles.items() if k == "Player"},
    }


@app.get("/game/next")
def next_event():
    if _io is None:
        return {"type": "error", "text": "No game running. POST /game/start first."}

    try:
        event = _io.event_queue.get(timeout=30)
        return event
    except queue.Empty:
        return {"type": "waiting", "message": "Generating..."}


@app.post("/game/respond")
def respond(body: RespondBody):
    if _io is None:
        return {"status": "error", "message": "No game running."}

    _io.response_queue.put(body.value)
    return {"status": "ok"}


@app.get("/game/state")
def game_state():
    if _gm is None:
        return {"status": "error", "message": "No game running."}

    state = _gm.state
    return {
        "day": state.day,
        "phase": state.phase.value if hasattr(state.phase, "value") else str(state.phase),
        "alive": list(state.alive_characters),
        "public_events": state.public_events[-10:],
        "chat_history": state.chat_history[-20:],
    }
