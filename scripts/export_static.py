"""Export a self-contained static snapshot of a paired run for the published demo.

    cd web && npm run build:static        # → web/dist-static (map layers come from public/geo)
    python scripts/export_static.py --scale 0.1 --warmup 60 --days 150   # → web/dist-static/data

The live API is reused through FastAPI's TestClient, so the static demo shows exactly what the
workstation shows. Cohort filtering, charts and cross-tabs work client-side; interactive stepping,
new interventions and server-side cohort explanations need the local app.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from ucsim.api import server
from ucsim.engine import runner

ROOT = Path(__file__).resolve().parents[1]


def dump(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, separators=(",", ":"), default=float, allow_nan=False) if not isinstance(obj, bytes) else None
    if data is None:
        path.write_bytes(obj)
        return len(obj)
    path.write_text(data, encoding="utf-8")
    return len(data)


def clean(x):
    """NaN/inf → None so the JSON is strict."""
    if isinstance(x, float):
        return x if np.isfinite(x) else None
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [clean(v) for v in x]
    return x


def interesting_people(sim, k: int, extra: list[int]) -> list[int]:
    """People with eventful lives (by salient events), plus a random sample and named extras."""
    log, reg, P = sim.log, sim.reg, sim.w.P
    sal = np.array([e.salience for e in reg.events.values()])
    m = sal[log["type"]] >= 0.6
    cnt = np.bincount(log["a"][m], minlength=P.n).astype(float)
    cnt[~P["present"].astype(bool)] = -1
    top = list(np.argsort(-cnt)[: k // 2])
    rng = np.random.default_rng(3)
    pool = np.where(P["present"])[0]
    rand = list(rng.choice(pool, k // 2, replace=False))
    out, seen = [], set()
    for i in [*extra, *top, *rand]:
        i = int(i)
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out[:k + len(extra)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--warmup", type=int, default=60)
    ap.add_argument("--days", type=int, default=150)
    ap.add_argument("--interventions", default="rent_up_20,new_dating_app")
    ap.add_argument("--people", type=int, default=240)
    ap.add_argument("--mc", action="store_true", help="also run a small Monte Carlo and sweep (slow)")
    ap.add_argument("--out", default=str(ROOT / "web" / "dist-static" / "data"))
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    t0 = time.time()
    WS = server.WS
    c = TestClient(server.app)

    print("building + warmup …")
    WS.base = runner.new_simulation(scale=a.scale, seed=a.seed)
    WS.base.run_days(a.warmup)
    presets = [p for p in a.interventions.split(",") if p]
    r = c.post("/api/fork", json={"interventions": [{"preset": p} for p in presets]})
    assert r.status_code == 200, r.text
    print(f"paired run {a.days} days …")
    WS.step(days=a.days)
    assert WS.job["state"] == "idle", WS.job
    sizes = {}

    def get(url, **params):
        r = c.get(url, params=params)
        assert r.status_code == 200, (url, r.status_code, r.text[:200])
        return r

    def put(name, obj):
        sizes[name] = dump(out / name, obj)

    put("registry.json", get("/api/registry").json())
    st = get("/api/status").json()
    st["static"] = True
    st["job"] = {"state": "idle"}
    put("status.json", st)
    put("presets.json", get("/api/interventions/presets").json())

    # ---- columns, bundled by domain (lazy-loaded per view)
    reg = WS.registry
    P = WS.base.w.P
    bundles: dict[str, list[str]] = {}
    for k, spec in P.specs.items():
        if spec.dtype == "str" or k in ("loc_lon", "loc_lat"):
            continue
        bundles.setdefault(spec.domain, []).append(k)
    index = {"columns": {}, "people": {}}
    for dom, vs in bundles.items():
        fname = f"{dom}.bin"
        for u in ("base", "alt"):
            put(f"cols/{u}/{fname}", get("/api/columns", vars=",".join(vs), u=u).content)
        for v in vs:
            index["columns"][v] = fname
    for u in ("base", "alt"):
        for mode in ("now", "home"):
            put(f"positions_{u}_{mode}.bin", get("/api/positions", u=u, mode=mode).content)

    # ---- comparison & causal graph (compare first so the graph carries deltas)
    cmp = get("/api/compare").json()
    put("compare.json", cmp)
    put("causal_graph.json", get("/api/causal_graph").json())

    # ---- people
    extra = [r["id"] for rows in cmp.get("most_affected", {}).values() for r in rows[:6]]
    featured = {u: get("/api/people/featured", u=u).json() for u in ("base", "alt")}
    for u, rows in featured.items():
        put(f"featured_{u}.json", rows)
        extra += [r["id"] for r in rows]
    people = interesting_people(WS.base, a.people, extra)
    shard, shard_no = {}, 0
    for k, i in enumerate(people):
        p = get(f"/api/person/{i}").json()
        p["network_full"] = get(f"/api/person/{i}/network").json()
        shard[str(i)] = p
        index["people"][str(i)] = shard_no
        if len(shard) == 24 or k == len(people) - 1:
            put(f"people/{shard_no}.json", shard)
            shard, shard_no = {}, shard_no + 1

    # ---- events: recent salient events with their causal chains
    ev = get("/api/events", min_salience=0.55, limit=1500).json()["events"]
    for e in ev:
        d = get(f"/api/event/{e['id']}").json()
        e["ancestors"] = d["ancestors"]
        e["descendants"] = d["descendants"][:15]
    put("events.json", {"total": len(ev), "events": ev})
    for u in ("base", "alt"):
        put(f"events_summary_{u}.json", get("/api/events/summary", u=u).json())

    # ---- flows over time: one "start -> middle -> now" Sankey per tracked variable
    for u in ("base", "alt"):
        info = get("/api/history/info", u=u).json()
        put(f"history_info_{u}.json", info)
        snaps = [d for d in info["days"] if d < info["now"]]
        days = sorted({0, snaps[len(snaps) // 2] if snaps else 0, info["now"]})
        flows = {}
        for var in info["categorical"]:
            r = c.post("/api/flows", json={"var": var, "days": days, "u": u})
            if r.status_code == 200:
                flows[var] = r.json()
        put(f"flows_{u}.json", flows)

    # ---- time series & mechanism terms (all groups)
    for kind, frame_fn in (("timeseries", "frame"), ("terms", "terms_frame")):
        obj = {}
        cols = None
        for u, sim in (("base", WS.base), ("alt", WS.alt)):
            df = getattr(sim.systems["recorder"], frame_fn)()
            cols = [x for x in df.columns if x not in ("day", "group", "n")]
            obj[u] = {}
            for g in df["group"].unique().to_list():
                sub = df.filter(df["group"] == g).drop("group")
                obj[u][g] = clean(sub.to_dict(as_series=False))
        obj["columns"] = cols
        put(f"{kind}.json", obj)

    # ---- places: per-complex/ward means for every mappable numeric variable
    map_vars = [k for k, s in P.specs.items() if s.dtype in ("f4", "f8", "bool", "u1", "u2", "i2") and ("map" in s.flags or "chart" in s.flags)]
    for u in ("base", "alt"):
        rows = {r["id"]: {**r, "means": {}} for r in get("/api/places/complexes", var="loneliness", u=u).json()}
        wrows = {r["id"]: {**r, "means": {}} for r in get("/api/places/wards", var="attend_rate", u=u).json()}
        sim = WS.sim(u)
        Pu = sim.w.P
        pres = Pu["present"].astype(bool)
        for v in map_vars:
            x = np.nan_to_num(Pu[v].astype(float))
            for key, rr in (("complex_id", rows), ("ward_id", wrows)):
                ids = Pu[key]
                m = pres & (ids >= 0)
                n = np.bincount(ids[m], minlength=1)
                s = np.bincount(ids[m], weights=x[m], minlength=len(n))
                for i_, r_ in rr.items():
                    if i_ < len(n) and n[i_]:
                        r_["means"][v] = round(float(s[i_] / n[i_]), 5)
        put(f"complexes_{u}.json", {"rows": list(rows.values())})
        put(f"wards_{u}.json", {"rows": list(wrows.values())})
        inst = {}
        for cid in list(rows)[:400]:
            j = get(f"/api/institution/complex/{cid}", u=u).json()
            j["members"] = j["members"][:60]
            inst[f"complex:{cid}"] = j
        for wid in wrows:
            j = get(f"/api/institution/ward/{wid}", u=u).json()
            j["members"] = j["members"][:60]
            inst[f"ward:{wid}"] = j
        for sid in (1, 2):
            j = get(f"/api/institution/school/{sid}", u=u).json()
            j["members"] = j["members"][:60]
            inst[f"school:{sid}"] = j
        put(f"institutions_{u}.json", clean(inst))
        put(f"network_sample_{u}.json", get("/api/network/sample", u=u, min_stage=3, max_nodes=900).json())
        put(f"origins_friends_{u}.json", get("/api/relationship_origins", u=u, min_stage=3).json())
        put(f"origins_romantic_{u}.json", get("/api/relationship_origins", u=u, min_stage=1, romantic=True).json())
    put("venues.json", get("/api/places/venues").json())

    # ---- Monte Carlo & sweep (optional; otherwise the lab shows instructions)
    if a.mc:
        print("monte carlo …")
        res = runner.monte_carlo({"baseline": [], "rent_up_20": [{"preset": "rent_up_20"}]}, seeds=[1, 2, 3, 4], days=90, scale=0.05, workers=4)
        res["state"] = "done"
        put("montecarlo.json", clean(res))
        print("sweep …")
        sw = runner.sweep("world:app_appeal", [0.6, 1.0, 1.4, 1.8], seeds=[1, 2], days=90, scale=0.05, workers=4)
        sw["state"] = "done"
        put("sweep.json", clean(sw))
    else:
        put("montecarlo.json", {"state": "none"})
        put("sweep.json", {"state": "none"})

    put("index.json", index)
    # static hosts may not serve raw binaries: ship every .bin (data and map layers) as base64 text
    import base64
    for f in list(out.parent.rglob("*.bin")):
        f.with_name(f.name + ".txt").write_bytes(base64.b64encode(f.read_bytes()))
        f.unlink()
    total = sum(sizes.values())
    big = sorted(sizes.items(), key=lambda kv: -kv[1])[:6]
    print(f"exported {len(sizes)} files, {total / 1e6:.1f} MB in {time.time() - t0:.0f}s; largest: {[(k, round(v / 1e6, 2)) for k, v in big]}")


if __name__ == "__main__":
    main()
