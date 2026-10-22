"""Speed and logs: how long each simulated day took (overall, per system, per world), this computer's measured speed for
the world-setup estimate, and the recent log lines, for the in-app Speed and Logs tools and the debug bundle.

Recording only reads clocks and `sim.timing`; it never touches the simulation's state or random streams, so runs are
identical with or without it.

    TELEMETRY.day(...)        one record per simulated day (the run loop in api/server.py calls it)
    TELEMETRY.summary()       last day, recent average, days per minute, what made slow days slow
    LOG.info(...)             the "ucsim" logger; every line is kept in memory (LOGBOOK) and, in the app, in a file
"""
from __future__ import annotations

import collections
import io
import json
import logging
import os
import platform
import sys
import threading
import time
import traceback
import zipfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG = logging.getLogger("ucsim")

# What each system does, in words (the Speed tool's labels).
SYSTEM_WORDS = {
    "environment": "weather and the calendar", "lifecourse": "births, missions, graduations, moves",
    "family": "family back home and trips", "honor": "the Honor Code", "academics": "classes and grades",
    "groups": "clubs and teams", "faith": "faith and church", "romance": "dating and relationships",
    "institutions": "counseling, bishops, employers", "occasions": "planning and going to things",
    "activity": "where everyone goes", "encounters": "who meets whom", "messaging": "texts and group chats",
    "mind": "thoughts, drives and memories", "coping": "coping", "plans": "personal plans", "emotion": "mood",
    "norms": "social norms", "network": "friendships", "culture": "complex culture", "intimacy": "intimacy",
    "routine": "habits", "economy": "money and jobs", "housing": "housing and moving",
    "recorder": "daily statistics", "history": "life-history snapshots",
}
# Work that happens only on some days, which is why those days are slower.
PERIODIC_WORDS = {
    "weekly": "Sunday night: the weekly updates (friendships, friend-group chats, faith, habits…)",
    "monthly": "last day of the month: rent, jobs and moves",
    "snapshot": "a life-history snapshot (every two weeks)",
}


def rss_mb() -> float | None:
    """This process's memory in use (resident set), in MB; None where it can't be read."""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/self/statm") as f:
                return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            c = PMC()
            c.cb = ctypes.sizeof(PMC)
            k32 = ctypes.WinDLL("kernel32")
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL("psapi")
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
                return c.WorkingSetSize / 2**20
            return None
        import resource                     # macOS: the peak, the best the standard library offers
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
    except Exception:  # noqa: BLE001
        return None


def periodic(sim, day: int) -> list[str]:
    """Which only-some-days work ran on simulated day `day` (see Simulation._phase and systems/history.py)."""
    out = []
    try:
        if sim.cal.weekday(day) == 6:
            out.append("weekly")
        if sim.cal.date(day + 1).day == 1:
            out.append("monthly")
        every = getattr(sim.systems.get("history"), "every", 14)
        if (day + 1) % every == 0:
            out.append("snapshot")
    except Exception:  # noqa: BLE001
        pass
    return out


class Telemetry:
    """Per-day speed records (the last few thousand days) and this computer's speed history."""

    KEEP = 4000

    def __init__(self):
        self.days: collections.deque = collections.deque(maxlen=self.KEEP)
        self.lock = threading.Lock()
        self.world: dict = {}
        self._cpu0 = None
        self.history_file: Path | None = None   # set by the app/server (data home); None in tests

    # ------------------------------------------------------------------ recording
    def new_world(self, scale: float, seed: int, people: int, build_s: float, warmup: int):
        with self.lock:
            self.days.clear()
            self.world = {"scale": scale, "seed": seed, "people": people, "build_s": round(build_s, 2), "warmup": warmup,
                          "built": time.time()}

    def day_begin(self) -> tuple[float, float]:
        return time.perf_counter(), time.process_time()

    def day(self, base, t0: tuple[float, float], timing_before: dict, *, alt=None, alt_s: float | None = None,
            alt_timing_before: dict | None = None, parallel: bool = False, pace: float = 0.0):
        """Record the day `base` just finished. `t0` is day_begin()'s value; `timing_before` a copy of base.timing from
        before the day (the systems' shares are the differences)."""
        wall = time.perf_counter() - t0[0]
        cpu = time.process_time() - t0[1]
        d = int(base.w.day) - 1                         # the day that was simulated (the clock now reads the next one)
        systems = {k: round(v - timing_before.get(k, 0.0), 4) for k, v in base.timing.items() if v - timing_before.get(k, 0.0) > 1e-5}
        alt_systems = None
        if alt is not None and alt_timing_before is not None:
            alt_systems = {k: round(v - alt_timing_before.get(k, 0.0), 4) for k, v in alt.timing.items() if v - alt_timing_before.get(k, 0.0) > 1e-5}
        base_s = sum(systems.values())
        rec = {"day": d, "date": str(base.cal.date(d)), "weekday": base.cal.date(d).strftime("%a"), "wall_s": round(wall, 3),
               "base_s": round(base_s, 3), "alt_s": round(alt_s, 3) if alt_s is not None else None, "parallel": bool(parallel),
               "cpu_pct": round(100 * cpu / wall, 0) if wall > 0 else None, "rss_mb": round(rss_mb() or 0, 0) or None,
               "people": int(base.w.P["present"].sum()), "systems": systems, "alt_systems": alt_systems,
               "periodic": periodic(base, d), "pace": pace, "t": time.time()}
        with self.lock:
            prior = [r["wall_s"] for r in list(self.days)[-14:] if not r["periodic"]]
            self.days.append(rec)
        if len(prior) >= 5:
            med = sorted(prior)[len(prior) // 2]
            if wall > 2.0 * med and wall > 0.5:
                why = self.why_slow(rec, prior_days=14)
                LOG.info("Day %s (%s) took %.2f s, %.1f× a usual day%s", rec["date"], rec["weekday"], wall, wall / med,
                         f": {why}" if why else "")
        return rec

    def why_slow(self, rec: dict, prior_days: int = 14) -> str:
        """The systems that took much longer than usual on this day, and the only-some-days work that ran, in words."""
        with self.lock:
            prior = [r for r in list(self.days)[-prior_days - 1:-1] if not r["periodic"]]
        parts = [PERIODIC_WORDS[p] for p in rec["periodic"]]
        if prior:
            extra = []
            for k, v in rec["systems"].items():
                usual = sorted(r["systems"].get(k, 0.0) for r in prior)[len(prior) // 2]
                if v - usual > 0.15 * rec["base_s"] and v > 1.8 * usual:
                    extra.append((v - usual, k))
            if extra:
                parts.append("longer than usual: " + ", ".join(f"{SYSTEM_WORDS.get(k, k)} (+{dv:.2f} s)" for dv, k in sorted(extra, reverse=True)[:3]))
        return "; ".join(parts)

    # ------------------------------------------------------------------ reading
    def summary(self) -> dict:
        """Last day, recent averages, days per minute and how the speed is changing."""
        with self.lock:
            rows = list(self.days)
        if not rows:
            return {"n": 0, "world": self.world}
        last = rows[-1]
        rec7 = rows[-7:]
        mean7 = sum(r["wall_s"] for r in rec7) / len(rec7)
        out = {"n": len(rows), "world": self.world, "last": {k: last[k] for k in ("day", "date", "weekday", "wall_s", "base_s", "alt_s",
                                                                                     "parallel", "cpu_pct", "rss_mb", "periodic")},
               "mean7_s": round(mean7, 3), "days_per_min": round(60 / mean7, 1) if mean7 > 0 else None,
               "why_last": self.why_slow(last) if last["periodic"] or len(rows) > 3 else ""}
        if len(rows) >= 21:                             # trend: the latest week against the first week measured
            first = [r["wall_s"] for r in rows[:7] if not r["periodic"]]
            late = [r["wall_s"] for r in rows[-7:] if not r["periodic"]]
            if first and late:
                out["trend"] = round(sum(late) / len(late) / (sum(first) / len(first)), 2)
        return out

    def brief(self) -> dict | None:
        """The few numbers the top bar shows (cheap: read on every status poll)."""
        with self.lock:
            if not self.days:
                return None
            rows = [self.days[-k] for k in range(1, min(30, len(self.days)) + 1)]
        last = rows[0]
        mean = sum(r["wall_s"] for r in rows[:7]) / len(rows[:7])
        return {"last_s": last["wall_s"], "mean7_s": round(mean, 3), "day": last["day"], "periodic": last["periodic"],
                "rss_mb": last["rss_mb"], "cpu_pct": last["cpu_pct"], "spark": [r["wall_s"] for r in reversed(rows)]}

    def records(self, since_day: int | None = None, limit: int = 400) -> list[dict]:
        with self.lock:
            rows = list(self.days)
        if since_day is not None:
            rows = [r for r in rows if r["day"] > since_day]
        return rows[-limit:]

    # ------------------------------------------------------------------ this computer's speed (setup estimate)
    def remember_speed(self):
        """Fold this world's measured Original-only speed into the per-computer history (by scale)."""
        f = self.history_file
        if f is None or not self.world:
            return
        with self.lock:
            rows = [r for r in self.days if r["alt_s"] is None and not r["periodic"]]
        if len(rows) < 5:
            return
        hist = self.speed_history()
        key = f"{self.world['scale']:.3f}"
        # early days and later days separately: days get slower as a world's records fill up
        early = [r["base_s"] for r in rows if r["day"] < 30]
        later = [r["base_s"] for r in rows if r["day"] >= 60]
        h = hist.get(key, {"scale": self.world["scale"]})
        if early:
            h["early_s"] = round(sorted(early)[len(early) // 2], 3)
        if later:
            h["later_s"] = round(sorted(later)[len(later) // 2], 3)
        h["people"] = self.world.get("people")
        h["build_s"] = self.world.get("build_s")
        h["updated"] = time.strftime("%Y-%m-%d")
        hist[key] = h
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(hist, indent=1), encoding="utf-8")
        except OSError:
            pass

    def speed_history(self) -> dict:
        f = self.history_file
        if f is None or not f.exists():
            return {}
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}


TELEMETRY = Telemetry()


# ---------------------------------------------------------------------- logs
class Logbook(logging.Handler):
    """The latest log lines in memory, numbered, for the Logs tool (`since` = the last id a page has)."""

    def __init__(self, keep: int = 3000):
        super().__init__(level=logging.INFO)
        self.lines: collections.deque = collections.deque(maxlen=keep)
        self.next_id = 0
        self._lk = threading.Lock()

    def emit(self, record: logging.LogRecord):
        try:
            msg = record.getMessage()
            if record.exc_info:
                msg += "\n" + "".join(traceback.format_exception(*record.exc_info)).rstrip()
            with self._lk:
                self.lines.append({"id": self.next_id, "t": record.created, "level": record.levelname.lower(),
                                   "source": record.name.removeprefix("ucsim.") if record.name != "ucsim" else "simulator",
                                   "msg": msg})
                self.next_id += 1
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def read(self, since: int = -1, level: str = "info", limit: int = 1000) -> list[dict]:
        order = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}
        lo = order.get(level, 1)
        with self._lk:
            rows = [r for r in self.lines if r["id"] > since and order.get(r["level"], 1) >= lo]
        return rows[-limit:]


LOGBOOK = Logbook()
_setup_done = False


def setup_logging(log_dir: Path | None = None):
    """Send the simulator's log lines (and Python warnings) to the in-memory logbook and, with `log_dir`, to a rotating
    file there (ucsim.log, 2 MB × 3). Safe to call more than once."""
    global _setup_done
    if not _setup_done:
        LOG.setLevel(logging.INFO)
        LOG.addHandler(LOGBOOK)
        LOG.propagate = False
        logging.captureWarnings(True)
        w = logging.getLogger("py.warnings")
        w.addHandler(LOGBOOK)
        w.propagate = False
        _setup_done = True
    if log_dir is not None and not any(isinstance(h, RotatingFileHandler) for h in LOG.handlers):
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(log_dir / "ucsim.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            LOG.addHandler(fh)
            logging.getLogger("py.warnings").addHandler(fh)
            TELEMETRY.history_file = log_dir.parent / "speed_history.json"
        except OSError:
            pass


setup_logging()


def log_dir_default() -> Path:
    """Where the app keeps its logs (%LOCALAPPDATA%/ProvoOremSimulator/logs, ~/.provo-orem-simulator/logs elsewhere);
    UCSIM_LOG_DIR overrides."""
    if os.environ.get("UCSIM_LOG_DIR"):
        return Path(os.environ["UCSIM_LOG_DIR"])
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) / "ProvoOremSimulator" if base else Path.home() / ".provo-orem-simulator") / "logs"


# ---------------------------------------------------------------------- debug bundle
def debug_bundle(world: dict, extra: dict | None = None) -> bytes:
    """A zip for a bug report: versions, the world's settings, speed records, the logbook and the log files.
    Holds no survey data and no people: only settings, timings and log lines."""
    import numpy

    buf = io.BytesIO()
    info = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "python": sys.version, "platform": platform.platform(),
            "machine": platform.machine(), "processor": platform.processor(), "cpus": os.cpu_count(),
            "numpy": numpy.__version__, "frozen_app": bool(getattr(sys, "frozen", False)), "world": world,
            "memory_mb": rss_mb(), **(extra or {})}
    try:
        from importlib.metadata import version
        info["ucsim"] = version("ucsim")
    except Exception:  # noqa: BLE001
        pass
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("about.json", json.dumps(info, indent=1, default=str))
        z.writestr("speed_summary.json", json.dumps(TELEMETRY.summary(), indent=1, default=str))
        z.writestr("speed_days.json", json.dumps(TELEMETRY.records(limit=TELEMETRY.KEEP), default=str))
        z.writestr("speed_history.json", json.dumps(TELEMETRY.speed_history(), indent=1))
        z.writestr("log_recent.txt", "\n".join(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r['t']))} {r['level'].upper()} "
                                               f"{r['source']}: {r['msg']}" for r in LOGBOOK.read(level="debug", limit=10_000)))
        for h in LOG.handlers:
            if not isinstance(h, RotatingFileHandler):
                continue
            base = Path(h.baseFilename)
            for p in sorted(base.parent.glob(base.name + "*")):
                try:
                    z.write(p, f"logs/{p.name}")
                except OSError:
                    pass
            app_log = base.parent.parent / "simulator.log"     # the console output of the windowed app (its tail)
            if app_log.exists():
                z.writestr("logs/simulator.log", app_log.read_bytes()[-2_000_000:])
    return buf.getvalue()
