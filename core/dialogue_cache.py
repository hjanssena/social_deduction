from concurrent.futures import ThreadPoolExecutor, Future


class DialoguePrefetcher:
    """Generates NPC dialogue in the background while the player reads the current one.

    Usage:
        prefetcher.submit(npc_controller.generate_assertion, speaker, assertion_idx)
        # ... player reads current dialogue ...
        result = prefetcher.get()  # blocks until ready, or returns None
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._future: Future | None = None
        self._meta: dict | None = None  # Extra data the caller needs alongside the result

    def submit(self, fn, *args, meta=None, **kwargs):
        """Run fn(*args, **kwargs) in background. Optionally attach metadata."""
        self._future = self._executor.submit(fn, *args, **kwargs)
        self._meta = meta

    def get(self, timeout=None):
        """Block until the prefetched result is ready. Returns (result, meta).
        Returns (None, None) if nothing was submitted."""
        if self._future is None:
            return None, None
        try:
            result = self._future.result(timeout=timeout)
        except Exception as e:
            import traceback
            print(f"\033[91m[Prefetcher] Background generation failed: {e}\033[0m")
            traceback.print_exc()
            result = None
        meta = self._meta
        self._future = None
        self._meta = None
        return result, meta

    def has_pending(self):
        return self._future is not None

    def invalidate(self):
        """Discard the prefetched result without blocking."""
        self._future = None
        self._meta = None

    def shutdown(self):
        self._executor.shutdown(wait=False)
