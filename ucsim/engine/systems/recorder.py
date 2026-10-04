"""Aggregate time series for analysis and comparison.

* daily: key variables, event counts and mechanism terms (the "vital signs")
* weekly: every chartable person field — means or category shares for each standard group, and
  percentiles for everyone — so any field can be followed over time and across universes.
"""
from __future__ import annotations

import numpy as np
import polars as pl

FIELD_EVERY = 7
PCTS = (10, 25, 50, 75, 90)


class Recorder:
    GROUPS = ("all", "BYU", "UVU", "F", "M", "single", "married")

    def __init__(self, sim):
        self.sim = sim
        self.rows: list[dict] = []
        self.event_rows: list[dict] = []
        self.term_rows: list[dict] = []
        self._ev_cursor = 0
        self.fields: dict = {"days": [], "groups": {}, "pct": {}}

    def init(self):
        reg = self.sim.reg
        self.vars = [v.id for v in reg.person_vars() if "timeseries" in v.flags]
        self.field_vars = [v.id for v in reg.person_vars()
                           if "chart" in v.flags and v.dtype != "str" and not v.id.endswith("_id")]
        self.field_snapshot(self.sim.w.day)

    # ------------------------------------------------------------------ weekly field aggregates
    def field_snapshot(self, label_day: int):
        """Group means / category shares of every chartable field (the state on the morning of label_day)."""
        P = self.sim.w.P
        F = self.fields
        if F["days"] and F["days"][-1] == label_day:
            return
        F["days"].append(int(label_day))
        groups = self._groups()
        for g, m in groups.items():
            G = F["groups"].setdefault(g, {"n": []})
            k = int(m.sum())
            G["n"].append(k)
            for v in self.field_vars:
                spec = P.specs[v]
                x = P[v][m]
                if spec.dtype == "cat":
                    val = (np.bincount(x, minlength=len(spec.categories))[: len(spec.categories)] / k).round(5).tolist() if k else None
                elif spec.dtype == "bool":
                    val = round(float(x.mean()), 5) if k else None
                else:
                    xf = x.astype(np.float64)
                    ok = np.isfinite(xf)
                    val = round(float(xf[ok].mean()), 5) if ok.any() else None
                G.setdefault(v, []).append(val)
        m = groups["all"]
        for v in self.field_vars:
            spec = P.specs[v]
            if spec.dtype in ("cat", "bool"):
                continue
            xf = P[v][m].astype(np.float64)
            xf = xf[np.isfinite(xf)]
            F["pct"].setdefault(v, []).append(np.percentile(xf, PCTS).round(5).tolist() if len(xf) else None)

    def _groups(self):
        P = self.sim.w.P
        pres = P["present"]
        return {
            "all": pres,
            "BYU": pres & (P["school"] == 1) & P["enrolled"],
            "UVU": pres & (P["school"] == 2) & P["enrolled"],
            "F": pres & P.is_("sex", "F"),
            "M": pres & P.is_("sex", "M"),
            "single": pres & P.isin("rel_status", ["single", "divorced", "talking"]),
            "married": pres & P.is_("rel_status", "married"),
        }

    def daily(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        day = w.day
        groups = self._groups()
        for g, m in groups.items():
            k = int(m.sum())
            row = {"day": day, "group": g, "n": k}
            if k:
                for v in self.vars:
                    x = P[v][m]
                    spec = P.specs[v]
                    if spec.dtype == "cat":
                        cats = spec.categories
                        cnt = np.bincount(x, minlength=len(cats)) / k
                        for c, val in zip(cats, cnt):
                            row[f"{v}={c}"] = float(val)
                    else:
                        xf = x.astype(np.float64)
                        ok = np.isfinite(xf)
                        row[v] = float(xf[ok].mean()) if ok.any() else None
            self.rows.append(row)
        # mechanism-term means (all present + by school) for population-level attribution
        emo = sim.systems["emotion"]
        for g in ("all", "BYU", "UVU", "single", "married"):
            m = groups[g]
            if not m.any():
                continue
            row = {"day": day, "group": g}
            for s, terms in emo.contrib.items():
                for t, arr in terms.items():
                    if len(arr) == len(m):
                        row[f"{s}.{t}"] = float(arr[m].mean())
                tr = emo.transient.get(s)
                if tr is not None and len(tr) == len(m):
                    row[f"{s}.events"] = float(tr[m].mean())
            self.term_rows.append(row)
        # event counts for today
        log = sim.log
        if log.n > self._ev_cursor:
            types = log["type"][self._ev_cursor: log.n]
            cnt = np.bincount(types, minlength=len(sim.reg.event_names))
            for code in np.nonzero(cnt)[0]:
                self.event_rows.append({"day": day, "event": sim.reg.event_names[code], "count": int(cnt[code])})
            self._ev_cursor = log.n
        # network size
        E = w.E
        st = E["stage"]
        self.rows.append({"day": day, "group": "_network", "n": int(E.n), "friend_ties": int((st >= 3).sum()),
                          "close_ties": int((st >= 4).sum())})
        if (day + 1) % FIELD_EVERY == 0:
            self.field_snapshot(day + 1)

    def frame(self) -> pl.DataFrame:
        return pl.DataFrame(self.rows, infer_schema_length=None)

    def events_frame(self) -> pl.DataFrame:
        if not self.event_rows:
            return pl.DataFrame({"day": [], "event": [], "count": []})
        return pl.DataFrame(self.event_rows)

    def terms_frame(self) -> pl.DataFrame:
        return pl.DataFrame(self.term_rows, infer_schema_length=None)
