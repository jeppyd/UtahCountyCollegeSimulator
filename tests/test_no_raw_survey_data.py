"""Guard: survey responses never enter the repository — only aggregates (cells of 10 or more) do.

Raw exports live in data/raw/ (gitignored) on the owner's machine. These checks fail if a raw export, a
respondent-level table, or anything that looks like survey response data or contact details is tracked by git."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Strings that appear in raw survey exports (Qualtrics metadata, question wording) but never in aggregates or code.
RAW_SIGNATURES = ("ResponseId", "Q_RecaptchaScore", "IPAddress", "RecipientEmail", "Duration (in seconds)",
                  "If you would like to be sent future surveys", "Response ID,Gender,Age")
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@(?!anthropic\.com|users\.noreply)[A-Za-z0-9.-]+\.(?:com|net|org|edu|io|us)\b")
DATA_EXT = (".csv", ".tsv", ".xlsx", ".xls", ".sav", ".dta", ".parquet")
# public geography and listings (UGRC, OSM, BYU's contracted-housing list), never survey data
ALLOWED_DATA = {"ucsim/geo/byu_contracted_2026_27.csv"}
ALLOWED_DIRS = ("ucsim/geo/data/", "ucsim/config/sources/")


def _tracked() -> list[str]:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p]


def test_no_raw_folders_tracked():
    bad = [p for p in _tracked() if p.startswith(("data/raw/", "data/derived/", "data/external/"))]
    assert not bad, f"raw or respondent-level files are tracked: {bad}"


def test_tracked_data_files_are_known_aggregates():
    """Every tracked data file is public geography or a small aggregate/source file under ucsim/config/sources/."""
    bad = []
    for p in _tracked():
        if p.lower().endswith(DATA_EXT) and p not in ALLOWED_DATA and not p.startswith(ALLOWED_DIRS):
            bad.append(p)
    assert not bad, f"unexpected data files tracked (add aggregates under ucsim/config/sources/ or the allowlist): {bad}"


def test_no_survey_response_signatures_or_emails():
    hits = []
    for p in _tracked():
        if p.startswith(("web/public/geo/", "tests/test_no_raw_survey_data.py")) or p.endswith((".png", ".ico", ".bin", ".parquet", ".npz")):
            continue
        f = ROOT / p
        if not f.is_file() or f.stat().st_size > 20_000_000:
            continue
        b = f.read_bytes()
        for sig in RAW_SIGNATURES:
            if sig.encode() in b:
                hits.append((p, sig))
        m = EMAIL.search(b)
        if m and p.startswith(("ucsim/priors/", "ucsim/config/")):
            hits.append((p, "email-like text"))
    assert not hits, f"tracked files look like they contain raw survey responses: {hits}"
