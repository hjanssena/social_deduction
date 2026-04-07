"""bridge.py — HTTP client that connects the Ren'Py frontend to the game server.

All network calls happen in a background thread so Ren'Py's main loop isn't
blocked.  Results land in a queue that the Ren'Py event loop drains.

Usage from Ren'Py (script.rpy):
    python:
        import bridge
        bridge.start_game()

    label game_loop:
        python:
            ev = bridge.next_event()
        # ... dispatch on ev["type"]
"""

import json
import threading
import queue

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError
except ImportError:
    # Ren'Py ships its own Python — should still have urllib
    raise

SERVER_URL = "http://127.0.0.1:8000"

# Queue of events from the server, consumed by the Ren'Py event loop.
_event_q = queue.Queue()
# Flag: True while we should keep polling.
_running = False


def _post(path, data=None, timeout=60):
    """POST JSON to the server and return the parsed response."""
    url = SERVER_URL + path
    body = json.dumps(data or {}).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(path, timeout=60):
    """GET from the server and return the parsed response."""
    url = SERVER_URL + path
    with urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_for_server(retries=120, interval=1):
    """Block until /health responds. Raises RuntimeError if it never comes up."""
    import time
    for _ in range(retries):
        try:
            _get("/health", timeout=2)
            return
        except Exception:
            time.sleep(interval)
    raise RuntimeError(f"Game server did not respond after {retries}s.")


def _poll_loop():
    """Background thread: long-polls GET /game/next and enqueues events."""
    global _running
    while _running:
        try:
            event = _get("/game/next")
            _event_q.put(event)
            # Stop polling after game_over
            if event.get("type") == "game_over":
                _running = False
        except Exception as e:
            _event_q.put({"type": "error", "text": str(e)})
            _running = False


def start_game():
    """Wait for the server, POST /game/start, then begin polling for events."""
    global _running
    wait_for_server()
    result = _post("/game/start", timeout=300)  # LLM load can take a while
    _running = True
    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()
    return result


def next_event(timeout=60):
    """Block until the next event arrives from the server (called from Ren'Py)."""
    try:
        return _event_q.get(timeout=timeout)
    except queue.Empty:
        return {"type": "waiting", "message": "Still generating..."}


def respond(value=""):
    """POST /game/respond with the player's input."""
    return _post("/game/respond", {"value": value})


def get_state():
    """GET /game/state — returns a snapshot of current game state."""
    return _get("/game/state")
