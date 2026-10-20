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
        names = list(groups)
        M = self._group_matrix(groups)
        ks = M.sum(axis=0)
        for gi, g in enumerate(names):
            F["groups"].setdefault(g, {"n": []})["n"].append(int(ks[gi]))
        for v in self.field_vars:
            spec = P.specs[v]
            vals = self._group_stats(P[v], spec, M, ks)
            for gi, g in enumerate(names):
                val = vals[gi]
                if isinstance(val, np.ndarray):
                    val = val.round(5).tolist()
                elif val is not None:
                    val = round(float(val), 5)
                F["groups"][g].setdefault(v, []).append(val)
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

    @staticmethod
    def _group_matrix(groups: dict) -> np.ndarray:
        """People × groups (0/1, float64): one matrix product then gives every group's sum at once."""
        return np.stack([m.astype(np.float64) for m in groups.values()], axis=1)

    @staticmethod
    def _group_stats(x: np.ndarray, spec, M: np.ndarray, ks: np.ndarray) -> list:
        """Per group: category shares (cat), the share true (bool) or the mean of finite values; None if empty."""
        G = M.shape[1]
        if spec.dtype == "cat":
            nc = len(spec.categories)
            oh = np.zeros((len(x), nc))
            ok = (x >= 0) & (x < nc)
            oh[np.flatnonzero(ok), x[ok].astype(np.int64)] = 1.0
            cnt = oh.T @ M                                          # categories × groups
            return [cnt[:, g] / ks[g] if ks[g] else None for g in range(G)]
        if spec.dtype == "bool":
            s_ = x.astype(np.float64) @ M
            return [s_[g] / ks[g] if ks[g] else None for g in range(G)]
        xf = x.astype(np.float64)
        fin = np.isfinite(xf)
        s_ = np.where(fin, xf, 0.0) @ M
        n_ = fin.astype(np.float64) @ M
        return [s_[g] / n_[g] if n_[g] else None for g in range(G)]

    def daily(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        day = w.day
        groups = self._groups()
        names = list(groups)
        M = self._group_matrix(groups)
        ks = M.sum(axis=0)
        rows = [{"day": day, "group": g, "n": int(ks[gi])} for gi, g in enumerate(names)]
        for v in self.vars:
            spec = P.specs[v]
            vals = self._group_stats(P[v], spec, M, ks)
            for gi in range(len(names)):
                if not ks[gi]:
                    continue
                val = vals[gi]
                if spec.dtype == "cat":
                    for c, cv in zip(spec.categories, val):
                        rows[gi][f"{v}={c}"] = float(cv)
                else:
                    rows[gi][v] = None if val is None else float(val)
        self.rows.extend(rows)
        # mechanism-term means (all present + by school) for population-level attribution
        emo = sim.systems["emotion"]
        tg = [names.index(g) for g in ("all", "BYU", "UVU", "single", "married")]
        Mt, kt = M[:, tg], ks[tg]
        trows = [{"day": day, "group": names[g]} for g in tg]
        for s, terms in emo.contrib.items():
            for t, arr in terms.items():
                if len(arr) == len(M):
                    sums = np.asarray(arr, np.float64) @ Mt
                    for j, r in enumerate(trows):
                        if kt[j]:
                            r[f"{s}.{t}"] = float(sums[j] / kt[j])
            tr = emo.transient.get(s)
            if tr is not None and len(tr) == len(M):
                sums = np.asarray(tr, np.float64) @ Mt
                for j, r in enumerate(trows):
                    if kt[j]:
                        r[f"{s}.events"] = float(sums[j] / kt[j])
        self.term_rows.extend(r for j, r in enumerate(trows) if kt[j])
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
