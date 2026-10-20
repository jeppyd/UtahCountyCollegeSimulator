"""The What-if world on a second processor core while time runs.

During a run the two worlds never touch each other, so `Workspace.step` can step the Original here while a worker
process steps the What-if, in lockstep, one day at a time (about half the wall time per day when comparing). The
worker holds the live What-if; the server keeps a copy for the pages, refreshed when someone looks at the What-if
(at most every few seconds) and always when the run ends or pauses. Anything that changes the What-if mid-run
(`Workspace.take_alt`) first brings the live copy back and the run carries on without the worker.

The world moves between processes by pickling (protocol 5). Results are bit-identical to stepping both worlds in one
process: the worker runs the same code on the same state with the same seeded random streams.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import pickle
import queue
import threading
import time
import traceback

MIN_DAYS = 3          # never for fewer days than this
COOLDOWN_DAYS = 5     # after the What-if was taken back mid-run, stay in one process this many days
PAYBACK = 2.5         # hand the What-if over only when the time saved is at least this many hand-overs
HANDOVER_GUESS_S = 3.0   # until one has been measured on this machine


def worth_it(days_left: int, alt_day_s: float | None, handover_s: float | None) -> bool:
    """Is a run long enough that stepping the What-if on a second core saves more than the hand-overs cost?"""
    if days_left < MIN_DAYS:
        return False
    if os.environ.get("UCSIM_PARALLEL", "").strip() == "force":
        return True
    if alt_day_s is None:                # not measured yet: long runs only
        return days_left >= 30
    return days_left * alt_day_s >= PAYBACK * 2 * (handover_s if handover_s else HANDOVER_GUESS_S)


def enabled() -> bool:
    """Parallel stepping is on when the machine has a second core (UCSIM_PARALLEL=0 turns it off, =1 forces it)."""
    v = os.environ.get("UCSIM_PARALLEL")
    if v is not None:
        return v.strip() not in ("0", "false", "off", "")
    return (os.cpu_count() or 1) >= 2


def _serve(conn):
    """Worker loop: holds one simulation and steps it on request."""
    sim = None
    while True:
        try:
            msg = conn.recv()
        except EOFError:
            return
        cmd = msg[0]
        try:
            if cmd == "load":
                sim = pickle.loads(conn.recv_bytes())
                conn.send(("ok", sim.w.day))
            elif cmd == "step":
                target = int(msg[1])
                t = time.perf_counter()
                sim.step_day()
                while sim.w.day < target:          # catch up if an earlier error left the What-if behind
                    sim.step_day()
                conn.send(("ok", (sim.w.day, time.perf_counter() - t)))
            elif cmd == "dump":
                conn.send(("ok", sim.w.day))
                conn.send_bytes(pickle.dumps(sim, protocol=pickle.HIGHEST_PROTOCOL))
            elif cmd == "drop":
                sim = None
                conn.send(("ok", None))
            elif cmd == "quit":
                conn.send(("ok", None))
                return
        except Exception as e:  # noqa: BLE001
            conn.send(("error", f"{e!r}", traceback.format_exc()))


class AltWorker:
    """A persistent worker process for the What-if world (started on first use, reused across runs).

    Messages go out through a sender thread (a large world never blocks the caller while the worker reads it);
    replies are read under `self.lock`, so the run loop and a request that takes the What-if back can both use it."""

    def __init__(self):
        self.proc = None
        self.conn = None
        self.lock = threading.Lock()
        self.busy = False          # a step was sent and its reply not yet read
        self.pending = 0           # replies to read before that one (an asynchronous load)
        self.last = None           # the last step's reply, for a caller whose step someone else collected
        self.last_handover_s = None
        self._q = None

    def _ensure(self):
        if self.proc is not None and self.proc.is_alive():
            return
        ctx = mp.get_context("spawn")             # never fork a process that runs server threads
        a, b = ctx.Pipe()
        self.proc = ctx.Process(target=_serve, args=(b,), name="ucsim-whatif", daemon=True)
        self.proc.start()
        self.conn = a
        self._q = queue.Queue()
        threading.Thread(target=self._sender, args=(a, self._q), daemon=True).start()

    @staticmethod
    def _sender(conn, q):
        while True:
            kind, item = q.get()
            if kind == "stop":
                return
            try:
                conn.send_bytes(item) if kind == "bytes" else conn.send(item)
            except Exception:  # noqa: BLE001  (the worker is gone: the reader sees it)
                return

    def _send(self, msg):
        self._q.put(("obj", msg))

    def _reply(self):
        r = self.conn.recv()
        if r[0] == "error":
            raise RuntimeError(f"the What-if worker failed: {r[1]}\n{r[2]}")
        return r[1]

    def _collect(self):
        """Read outstanding replies (under self.lock)."""
        while self.pending:
            self.pending -= 1
            self._reply()
        if self.busy:
            self.last = self._reply()
            self.busy = False

    def load(self, sim, wait: bool = True) -> None:
        """Send the world to the worker. With wait=False the worker unpacks it while this process gets on with the
        Original's day; the next `wait()` collects both replies."""
        with self.lock:
            self._ensure()
            blob = pickle.dumps(sim, protocol=pickle.HIGHEST_PROTOCOL)
            self._send(("load",))
            self._q.put(("bytes", blob))
            del blob
            self.pending += 1
            if wait:
                self._collect()

    def step_async(self, target_day: int) -> None:
        with self.lock:
            self._send(("step", int(target_day)))
            self.busy = True

    def wait(self) -> tuple[int, float]:
        """(the What-if's day, seconds its step took) once the step sent by `step_async` is done."""
        with self.lock:
            self._collect()
            return self.last

    def fetch(self):
        """A copy of the worker's world as it is now (after any step in flight; the worker keeps its own)."""
        with self.lock:
            self._collect()
            t = time.perf_counter()
            self._send(("dump",))
            self._reply()
            sim = pickle.loads(self.conn.recv_bytes())
            self.last_handover_s = time.perf_counter() - t
            return sim

    def drop(self) -> None:
        with self.lock:
            if self.proc is not None and self.proc.is_alive():
                self._collect()
                self._send(("drop",))
                self._reply()

    def close(self) -> None:
        with self.lock:
            if self.proc is not None and self.proc.is_alive():
                try:
                    self._send(("quit",))
                    self.proc.join(timeout=5)
                except Exception:  # noqa: BLE001
                    pass
                if self.proc.is_alive():
                    self.proc.terminate()
            if self._q is not None:
                self._q.put(("stop", None))
            self.proc = None
