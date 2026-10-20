"""Entity index: everything a person can point at in a What-if, resolved to an exact id and a population filter.

Kinds: person, complex, venue, venue_type, ward, employer, club, team, institute, congregation, major, neighborhood,
city, school, and model concepts (field, event, rule, preset). Each entry is
    {kind, id, ref: "kind:id", label, sub, n (people linked now, when meaningful), who (population filter or None)}
"""
from __future__ import annotations

import re

import numpy as np

from ..analysis.person import FIRST_F, FIRST_M, LAST, headline
from ucsim.population.structure import ward_name

PLACE_KINDS = ("complex", "venue", "venue_type", "ward", "employer", "club", "team", "institute", "congregation", "major",
               "neighborhood", "city", "school")
CONCEPT_KINDS = ("field", "event", "rule", "preset")
LINK = {"complex": "complex_id", "ward": "ward_id", "employer": "employer_id", "club": "club_id", "team": "team_id",
        "institute": "institute_class", "congregation": "congregation_id", "major": "major_id"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(s).lower()).strip()


def _score(q: str, label: str, extra: str = "") -> float:
    """Prefix > word-boundary > substring > all words present > subsequence."""
    if not q:
        return 1.0
    lab = _norm(label)
    if lab == q:
        return 100.0
    if lab.startswith(q):
        return 80.0 - 0.1 * len(lab)
    if f" {q}" in f" {lab}":
        return 60.0 - 0.1 * len(lab)
    if q in lab:
        return 45.0 - 0.1 * len(lab)
    hay = f"{lab} {_norm(extra)}"
    words = q.split()
    if words and all(w in hay for w in words):
        return 35.0 - 0.1 * len(lab)
    it = iter(lab)
    if len(q) >= 3 and all(c in it for c in q.replace(" ", "")):
        return 10.0 - 0.05 * len(lab)
    return 0.0


class EntityIndex:
    """Built per world (and rebuilt when the world changes); people are searched live."""

    def __init__(self, sim):
        self.sim = sim
        self.rows: list[dict] = []
        self._build()

    # ------------------------------------------------------------------ build
    def _counts(self, col: str, size: int) -> np.ndarray:
        P = self.sim.w.P
        x = P[col]
        m = P["present"].astype(bool) & (x >= 0)
        return np.bincount(x[m].astype(np.int64), minlength=size) if size else np.zeros(0, int)

    def _build(self):
        sim = self.sim
        w = sim.w
        P = w.P
        reg = sim.reg
        rows = self.rows
        U = w.units
        cx = w.complexes
        uin = np.bincount(U.complex_id[U.complex_id >= 0], minlength=cx.height)
        beds = np.bincount(U.complex_id[U.complex_id >= 0], weights=U.capacity[U.complex_id >= 0].astype(float), minlength=cx.height)
        live = P["present"].astype(bool) & (P["unit_id"] >= 0)
        uid = P["unit_id"][live]
        res = np.bincount(U.complex_id[uid][U.complex_id[uid] >= 0], minlength=cx.height)
        names, kinds, src, contracted = cx["name"].to_list(), cx["kind"].to_list(), cx["name_src"].to_list(), cx["contracted"].to_list()
        for c in range(cx.height):
            if kinds[c] == "special_dup" or uin[c] == 0:
                continue
            generic = src[c] == "address"
            sub = f"{kinds[c].replace('_', ' ')}{' · BYU-contracted' if contracted[c] else ''} · {int(uin[c])} units, {int(beds[c])} beds"
            rows.append({"kind": "complex", "id": c, "label": names[c], "sub": sub, "n": int(res[c]), "generic": generic,
                         "who": {"var": "complex_id", "op": "eq", "value": c}})
        act = sim.systems["activity"]
        vt = act.v_type
        vn = act.v_name
        for v in range(len(vn)):
            t = str(vt[v])
            visited = t != "closed"
            rows.append({"kind": "venue", "id": v, "label": vn[v], "sub": f"{t.replace('_', ' ')}{'' if visited else ' (closed)'}",
                         "n": None, "who": None})
        for t in sorted(set(str(x) for x in vt)):
            if t == "closed":
                continue
            k = int((vt == t).sum())
            rows.append({"kind": "venue_type", "id": t, "label": f"All {t.replace('_', ' ')}s", "sub": f"{k} venues", "n": None, "who": None})
        wk = w.wards["kind"]
        wn = self._counts("ward_id", len(wk))
        for i in range(len(wk)):
            if wn[i] == 0:
                continue
            on = " (meets on campus)" if int(w.wards["meetinghouse"][i]) < 0 else ""
            rows.append({"kind": "ward", "id": i, "label": ward_name(w.wards, i),
                         "sub": f"LDS ward{on} · {int(wn[i])} members", "n": int(wn[i]), "who": {"var": "ward_id", "op": "eq", "value": i}})
        E = w.employers
        en = self._counts("employer_id", len(E["type"]))
        for i in range(len(E["type"])):
            if en[i] == 0:
                continue
            rows.append({"kind": "employer", "id": i, "label": str(E["name"][i]), "sub": f"{str(E['type'][i]).replace('_', ' ')} · {int(en[i])} employees",
                         "n": int(en[i]), "who": {"var": "employer_id", "op": "eq", "value": i}})
        G = w.groups
        cols = {"club": self._counts("club_id", len(G["kind"])), "team": self._counts("team_id", len(G["kind"])),
                "institute": self._counts("institute_class", len(G["kind"]))}
        for i in range(len(G["kind"])):
            kd = str(G["kind"][i])
            n = int(cols[kd][i]) if kd in cols else 0
            school = {1: "BYU", 2: "UVU"}.get(int(G["school"][i]), "")
            rows.append({"kind": kd, "id": i, "label": str(G["name"][i]), "sub": f"{kd} · {school} · {n} members", "n": n,
                         "who": {"var": LINK[kd], "op": "eq", "value": i}})
        C = w.congregations
        cn = self._counts("congregation_id", len(C["name"]))
        for i in range(len(C["name"])):
            rows.append({"kind": "congregation", "id": i, "label": str(C["name"][i]), "sub": f"{C['affiliation'][i]} congregation · {int(cn[i])} attend",
                         "n": int(cn[i]), "who": {"var": "congregation_id", "op": "eq", "value": i}})
        from ..population.majors import catalog
        maj = catalog()
        mn = self._counts("major_id", len(maj))
        for m in maj:
            n = int(mn[m["id"]]) if m["id"] < len(mn) else 0
            if n == 0:
                continue
            rows.append({"kind": "major", "id": m["id"], "label": f"{m['major']} ({m['school']})", "sub": f"major · {m.get('college', '')} · {n} students",
                         "n": n, "who": {"var": "major_id", "op": "eq", "value": m["id"]}})
        pres = P["present"].astype(bool)
        for var, kind in (("neighborhood", "neighborhood"), ("city", "city")):
            cats = P.specs[var].categories
            cnt = np.bincount(P[var][pres], minlength=len(cats))
            for c, lab in enumerate(cats):
                if cnt[c]:
                    rows.append({"kind": kind, "id": lab, "label": lab, "sub": f"{kind} · {int(cnt[c])} residents", "n": int(cnt[c]),
                                 "who": {"var": var, "op": "eq", "value": lab}})
        for code, lab in ((1, "BYU"), (2, "UVU")):
            n = int((pres & (P["school"] == code) & P["enrolled"]).sum())
            rows.append({"kind": "school", "id": lab, "label": lab, "sub": f"university · {n} enrolled students", "n": n,
                         "who": {"and": [{"var": "school", "op": "eq", "value": lab}, {"var": "enrolled", "op": "eq", "value": True}]}})
        for vid, v in reg.variables.items():
            if getattr(v, "entity", "person") == "person" and v.flags:
                rows.append({"kind": "field", "id": vid, "label": v.label, "sub": f"field · {v.kind}", "n": None, "who": None})
        for eid, e in reg.events.items():
            if e.category not in ("intervention",):
                rows.append({"kind": "event", "id": eid, "label": e.label, "sub": f"event · {e.category}", "n": None, "who": None})
        for mid, m in reg.mechanisms.items():
            if m.system != "whatif":
                rows.append({"kind": "rule", "id": mid, "label": m.label, "sub": f"rule · {m.system} · {m.evidence}", "n": None, "who": None})
        from ..engine.interventions import load_presets
        for pid, pr in load_presets().items():
            rows.append({"kind": "preset", "id": pid, "label": pr.get("name", pid), "sub": "ready-made What-if", "n": None, "who": None})
        for r in rows:
            r["ref"] = f"{r['kind']}:{r['id']}"
            r["_n"] = _norm(r["label"])

    # ------------------------------------------------------------------ people
    def people(self, q: str, limit: int = 8) -> list[dict]:
        P = self.sim.w.P
        q = q.strip().lower().lstrip("#")
        out = []
        if q.isdigit():
            i = int(q)
            if 0 <= i < P.n:
                out.append(self.person_row(i, 100.0))
            return out
        n = P.n
        h = (np.arange(n, dtype=np.uint64) * np.uint64(2654435761)) & np.uint64(0xFFFFFFFF)
        female = P["sex"] == P.code("sex", "F")
        fi = (h % np.uint64(24)).astype(int)
        li = ((h >> np.uint64(8)) % np.uint64(len(LAST))).astype(int)
        first = np.where(female, np.array(FIRST_F, dtype=object)[fi], np.array(FIRST_M, dtype=object)[fi])
        full = np.char.lower((first.astype(str).astype(object) + " " + np.array(LAST, dtype=object)[li]).astype(str))
        words = q.split()
        m = P["present"].astype(bool)
        for wd in words:
            m &= np.char.find(full, wd) >= 0
        for i in np.where(m)[0][: limit]:
            out.append(self.person_row(int(i), 50.0))
        return out

    def person_row(self, i: int, score: float = 0.0) -> dict:
        from ..analysis.person import synthetic_name
        P = self.sim.w.P
        try:
            sub = headline(self.sim, i)
        except Exception:  # noqa: BLE001
            sub = f"person #{i}"
        return {"kind": "person", "id": i, "ref": f"person:{i}", "label": synthetic_name(P, i), "sub": f"#{i} · {sub}", "n": 1,
                "who": {"ids": [i]}, "score": score}

    # ------------------------------------------------------------------ search
    def search(self, q: str, kinds: list[str] | None = None, limit: int = 12) -> list[dict]:
        qn = _norm(q)
        want = set(kinds) if kinds else None
        scored = []
        for r in self.rows:
            if want and r["kind"] not in want:
                continue
            s = _score(qn, r["label"], r["sub"])
            if s <= 0:
                continue
            # prefer real places people live/meet in over concept rows and generic address-named complexes
            s += 3.0 if r["kind"] in PLACE_KINDS else 0.0
            s -= 8.0 if r.get("generic") else 0.0
            s += min((r.get("n") or 0) / 200.0, 3.0)
            scored.append((s, r))
        scored.sort(key=lambda t: -t[0])
        out = [{k: v for k, v in r.items() if not k.startswith("_")} | {"score": round(s, 1)} for s, r in scored[:limit]]
        if (not want or "person" in want) and qn:
            ppl = self.people(q, limit=max(3, limit // 3))
            out = sorted(out + ppl, key=lambda r: -r.get("score", 0))[:limit]
        return out

    def get(self, ref: str) -> dict | None:
        kind, _, rid = ref.partition(":")
        if kind == "person":
            return self.person_row(int(rid)) if rid.isdigit() and int(rid) < self.sim.w.P.n else None
        for r in self.rows:
            if r["kind"] == kind and str(r["id"]) == rid:
                return {k: v for k, v in r.items() if not k.startswith("_")}
        return None
