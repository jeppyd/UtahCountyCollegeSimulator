"""strftime flags like %-d (no padding) work on Linux but raise "Invalid format string" on Windows,
where the app ships. A pair scene broke this way, so keep them out of the package."""
import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "ucsim"
BAD = re.compile(r"%[-#][a-zA-Z]")


def test_no_platform_specific_strftime_flags():
    hits = [f"{p.relative_to(PKG.parent)}:{i}: {line.strip()}"
            for p in PKG.rglob("*.py")
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if ("strftime" in line or re.search(r"\{[^}]*:%", line)) and BAD.search(line)]
    assert not hits, "non-portable strftime flags:\n" + "\n".join(hits)
