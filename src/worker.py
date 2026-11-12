"""A tiny helper process that runs the quantum simulation for the app.

Why: Streamlit re-runs the page on a new thread for every click. The solver
is kept in ONE separate, long-lived Python process instead, so all Qiskit
work happens on that process's main thread. The app talks to it over its
stdin/stdout pipes using pickled messages:

    app  -> worker : (function_name, args)
    worker -> app  : ("ok", result)  or  ("error", message)

Run as a server with:  python -m src.worker   (the app does this for you)
"""
import pickle
import subprocess
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent   # folder containing src/


class Worker:
    """Client side: starts the helper process and sends it requests."""

    def __init__(self):
        self._lock = threading.Lock()     # one request at a time
        self._process = None

    def _start(self):
        self._process = subprocess.Popen(
            [sys.executable, "-m", "src.worker"], cwd=PROJECT_ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def _request(self, name, args):
        pickle.dump((name, args), self._process.stdin)
        self._process.stdin.flush()
        return pickle.load(self._process.stdout)

    def call(self, name, *args):
        """Run service.<name>(*args) in the helper and return its result.
        If the helper has died, start a new one and try once more."""
        with self._lock:
            for attempt in (1, 2):
                if self._process is None or self._process.poll() is not None:
                    self._start()
                try:
                    status, value = self._request(name, args)
                    break
                except (EOFError, BrokenPipeError, OSError):
                    self._process = None          # helper died mid-request
                    if attempt == 2:
                        raise RuntimeError("The quantum solver process stopped unexpectedly.")
        if status == "error":
            raise RuntimeError(value)
        return value


def main():
    """Server side: answer requests until the app closes the pipe."""
    from . import service                 # imports Qiskit; only the helper needs it
    replies = sys.stdout.buffer           # keep the real stdout for replies only
    sys.stdout = sys.stderr               # any stray print() goes to stderr instead
    requests = sys.stdin.buffer
    while True:
        try:
            name, args = pickle.load(requests)
        except EOFError:                  # app exited
            return
        try:
            reply = ("ok", getattr(service, name)(*args))
        except Exception as exc:          # report the problem instead of dying
            reply = ("error", f"{type(exc).__name__}: {exc}")
        pickle.dump(reply, replies)
        replies.flush()


if __name__ == "__main__":
    main()
