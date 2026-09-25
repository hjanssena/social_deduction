"""A single background worker for LLM work the player shouldn't wait on (log entries, compaction).

Its calls are marked as background, so the LLM's priority gate always serves foreground calls first.
Tasks run in submission order; wait_idle() blocks until everything queued so far is done.
"""
import queue
import threading
import traceback

from services.llm_base import BACKGROUND


class BackgroundWorker:
    def __init__(self):
        self._tasks = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="llm-background", daemon=True)
        self._thread.start()

    def submit(self, fn, *args, **kwargs):
        self._tasks.put((fn, args, kwargs))

    def wait_idle(self):
        """Blocks until every task submitted so far has finished."""
        self._tasks.join()

    def pending(self) -> int:
        return self._tasks.unfinished_tasks

    def _run(self):
        BACKGROUND.active = True
        while True:
            fn, args, kwargs = self._tasks.get()
            try:
                fn(*args, **kwargs)
            except Exception as e:
                print(f"\033[91m[Background] {getattr(fn, '__name__', fn)} failed: {e}\033[0m", flush=True)
                traceback.print_exc()
            finally:
                self._tasks.task_done()
