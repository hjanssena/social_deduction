"""PyInstaller entry point for the game server.

When packaged, this is the executable that Ren'Py launches.
Equivalent to: uvicorn server.app:app --host 127.0.0.1 --port 8000
"""

import uvicorn
from server.app import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
