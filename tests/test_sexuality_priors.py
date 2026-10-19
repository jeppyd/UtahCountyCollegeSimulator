"""The LDS Sexuality Survey's committed aggregates: privacy (cells ≥ 10, no long arrays, no free text) and the
builder's boundaries (it refuses without the raw file and rewrites only its own sections)."""
import json
from pathlib import Path

import pytest

from ucsim.ingest import sexuality as S
from ucsim.ingest.priors import K_MIN
from ucsim.ingest.survey_spec import SEXUALITY_SPEC

PRIORS = Path(__file__).resolve().parents[1] / "ucsim" / "priors" / "survey_priors.json"
FREE_TEXT = ("other - text", "fantasy", "favorite", "wildest", "anything else", "city", "college", "birth control",
             "position", "how do you end", "use when having sex", "wish you could engage")


def _ours():
    pri = json.loads(PRIORS.read_text(encoding="utf-8"))
    secs = {"block": pri["blocks"][S.BLOCK],
            "targets": {k: v for k, v in pri["targets"].items() if k.startswith(S.PREFIX)},
            "tables": {k: v for k, v in pri["tables"].items() if k.startswith(S.PREFIX)},
            "source": pri["meta"]["sources"][S.SLUG]}
    return pri, secs


def _walk(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from _walk(v)
    elif isinstance(x, list):
        yield x
        for v in x:
            yield from _walk(v)
    else:
        yield x


def test_spec_never_reads_free_text_or_excluded_items():
    for header in SEXUALITY_SPEC["vars"]:
        assert not any(w in header for w in FREE_TEXT), header


def test_committed_cells_have_at_least_k_min_respondents():
    _, o = _ours()
    for v, m in o["block"]["marginals"].items():
        for s in ("M", "F"):
            assert m[f"n_{s}"] == 0 or m[f"n_{s}"] >= K_MIN, (v, s)
            if m["kind"] != "num" and m[s] is not None and m[f"n_{s}"]:
                # a level's share times n is a head count: either ≥ K_MIN or only the smoothing pseudo-count
                for p in m[s]:
                    assert p * m[f"n_{s}"] >= K_MIN or p * m[f"n_{s}"] < 1, (v, s, p)
    for name, rows in o["targets"].items():
        for r in (rows if isinstance(rows, list) else [x for v in rows.values() for x in v]):
            assert r["n_band"] in ("10-29", "30-99", "100-299", "300+"), (name, r)
    assert o["block"]["min_pair_n"] >= 30
    assert o["source"]["n_band"] in ("300+", "100-299")


def test_no_long_arrays_and_no_free_text():
    _, o = _ours()
    for x in _walk(o):
        if isinstance(x, list):
            assert len(x) <= 99 or all(isinstance(r, list) for r in x)     # quantile grids at most; corr rows
        if isinstance(x, str):
            assert len(x) < 400, x[:60]
            assert not any(w in x.lower() for w in ("fantasy", "wildest", "sex hack")), x[:60]


def test_builder_refuses_without_the_raw_file(monkeypatch, tmp_path):
    monkeypatch.setattr(S, "RAW_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        S.load()


def test_merge_rewrites_only_its_own_sections(tmp_path):
    pri, o = _ours()
    p = tmp_path / "priors.json"
    p.write_text(json.dumps(pri), encoding="utf-8")
    out = {"block": {"name": S.BLOCK, "variables": []}, "targets": {"x": []}, "tables": {"y": {}}, "source": {"title": "t"}}
    new = S.merge_into_priors(out, p)
    for sec in ("skeleton", "blocks", "targets", "tables"):
        for k, v in pri[sec].items():
            if not (k == S.BLOCK or k.startswith(S.PREFIX)):
                assert new[sec][k] == v, (sec, k)
    assert {k for k in new["targets"] if k.startswith(S.PREFIX)} == {S.PREFIX + "x"}
    for k, v in pri["meta"]["sources"].items():
        if k != S.SLUG:
            assert new["meta"]["sources"][k] == v
