"""Per-person history: compact snapshots of key states every couple of weeks.

Enables flows (who moved from state A to state B between two dates), transition cohorts
("people who went from single to married since September") and cohort trajectories ("how did
today's lonely people get here?"). Categorical/bool variables are stored as uint8 codes and numeric
ones as float16, so a 4-year run at scale 0.3 stays well under 100 MB.

A snapshot labelled day d is the state on the morning of day d (taken at the end of day d − 1).
"""
from __future__ import annotations

import numpy as np

ABSENT = 255  # code for "not in Provo/Orem at that time" (not yet arrived, away on a mission, left)


class History:
    def __init__(self, sim):
        self.sim = sim
        self.snaps: list[dict] = []

    def init(self):
        cfg = self.sim.w.cfg.get("history", {})
        P = self.sim.w.P
        self.every = int(cfg.get("every_days", 14))
        self.cat_vars = [v for v in cfg.get("categorical", []) if v in P.specs and P.specs[v].dtype in ("cat", "bool")]
        self.num_vars = [v for v in cfg.get("numeric", []) if v in P.specs and P.specs[v].dtype not in ("cat", "bool", "str")]
        # float16 keeps ~3 significant digits up to 65k: fine for 0–1 states and counts, not for dollars
        self.num_dtype = {v: (np.float32 if (P.specs[v].range and max(map(abs, P.specs[v].range)) > 6e4) or
                              (P.specs[v].units or "").lower() in ("usd", "$", "dollars") else np.float16) for v in self.num_vars}
        self.take(self.sim.w.day)

    def take(self, label_day: int):
        P = self.sim.w.P
        n = P.n
        snap = {"day": int(label_day), "n": n, "present": P["present"][:n].astype(bool).copy()}
        for v in self.cat_vars:
            snap[v] = P[v][:n].astype(np.uint8).copy()
        for v in self.num_vars:
            snap[v] = P[v][:n].astype(self.num_dtype[v])
        # where people lived, for map playback (float32 ≈ 1 m precision here)
        snap["home_lon"] = P["home_lon"][:n].astype(np.float32)
        snap["home_lat"] = P["home_lat"][:n].astype(np.float32)
        if self.snaps and self.snaps[-1]["day"] == snap["day"]:
            self.snaps[-1] = snap
        else:
            self.snaps.append(snap)

    def daily(self):
        nxt = self.sim.w.day + 1
        if nxt % self.every == 0:
            self.take(nxt)

    # ------------------------------------------------------------------ queries
    def days(self) -> list[int]:
        return [s["day"] for s in self.snaps]

    def tracked(self, var: str) -> bool:
        return var in self.cat_vars or var in self.num_vars

    def snapshot(self, day: int) -> dict:
        """The latest snapshot at or before `day` (the first one if `day` is earlier)."""
        best = self.snaps[0]
        for s in self.snaps:
            if s["day"] <= day:
                best = s
        return best

    def values(self, var: str, day: int | None = None):
        """(values, present) for every current person at `day` (None = now). Rows created after the
        snapshot are reported absent; categorical values of absent people are ABSENT."""
        P = self.sim.w.P
        n = P.n
        if day is None or day >= self.sim.w.day:
            pres = P["present"][:n].astype(bool)
            x = P[var][:n]
            if P.specs[var].dtype in ("cat", "bool"):
                x = np.where(pres, x.astype(np.uint8), ABSENT).astype(np.uint8)
            return x, pres
        s = self.snapshot(day)
        m = s["n"]
        pres = np.zeros(n, bool)
        pres[:m] = s["present"]
        if var in self.cat_vars:
            x = np.full(n, ABSENT, np.uint8)
            x[:m] = np.where(s["present"], s[var], ABSENT)
            return x, pres
        if var in self.num_vars:
            x = np.full(n, np.nan, np.float32)
            x[:m] = s[var].astype(np.float32)
            x[~pres] = np.nan
            return x, pres
        raise KeyError(f"{var} is not tracked in history")

    def homes(self, s: dict) -> tuple[np.ndarray, np.ndarray]:
        """Home coordinates for every current person at snapshot `s` (NaN if absent)."""
        n = self.sim.w.P.n
        m = s["n"]
        lon = np.full(n, np.nan, np.float32)
        lat = np.full(n, np.nan, np.float32)
        if "home_lon" in s:
            lon[:m] = np.where(s["present"], s["home_lon"], np.nan)
            lat[:m] = np.where(s["present"], s["home_lat"], np.nan)
        return lon, lat

    def nbytes(self) -> int:
        return sum(a.nbytes for s in self.snaps for a in s.values() if isinstance(a, np.ndarray))
