"""The Psych 308 survey (BYU, 2020) enters only as aggregates (cells of K_MIN or more, no free text or ids), and the
model is checked against it (levels held out, pandemic-era levels as diagnostics, associations as patterns)."""
import json

from ucsim.analysis.psych308_check import SRC, rows
from ucsim.engine.runner import new_simulation
from ucsim.ingest.priors import K_MIN


def test_aggregates_only():
    d = json.loads(SRC.read_text(encoding="utf-8"))
    assert d["meta"]["k_min"] == K_MIN
    for sec in ("stable", "pandemic"):
        for var, groups in d[sec].items():
            for g, cell in groups.items():
                assert cell["summary"]["n"] >= K_MIN, (var, g)
                for code, share in cell.get("shares", {}).items():
                    assert share * cell["summary"]["n"] >= K_MIN - 0.5, (var, g, code)
    assert all(a["n"] >= 30 for a in d["associations"])
    text = SRC.read_text(encoding="utf-8")
    assert "_TEXT" not in text and "StartDate" not in text


def test_model_rows():
    sim = new_simulation(scale=0.05, seed=2)
    sim.run_days(5)
    r = rows(sim)
    kinds = {x["kind"] for x in r}
    assert {"holdout", "diagnostic", "pattern"} <= kinds
    assert all(x["status"] in ("pass", "warn", "fail", "n/a") for x in r)
