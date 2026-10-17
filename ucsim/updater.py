"""In-app updates for the installed Windows app.

The app asks GitHub for the latest release, compares its version with the one stamped into this build
(`ucsim/_build_version.py`, written by the release workflow), downloads the new installer, checks its size and
SHA-256 against what GitHub reports, runs it silently and quits; the installer replaces the files and starts the
new version. Running from source there is nothing to install: `git pull` instead.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = os.environ.get("UCSIM_UPDATE_REPO", "jeppyd/UtahCountyCollegeSimulator")
ASSET = "ProvoOremSimulator-Setup.exe"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
WINDOWS = sys.platform == "win32"

try:
    from ._build_version import VERSION as CURRENT     # stamped by the release build
except ImportError:
    CURRENT = None

_lock = threading.Lock()
_cache: dict = {}
STATE: dict = {"state": "idle"}           # idle | downloading | installing | error


def _vtuple(v: str | None) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def installable() -> bool:
    return bool(getattr(sys, "frozen", False)) and WINDOWS and CURRENT is not None


def check(force: bool = False) -> dict:
    """{current, latest, available, notes, published, can_install, error?}; cached for 10 minutes."""
    hit = _cache.get("check")
    if hit and not force and time.time() - hit[0] < 600:
        return {**hit[1], "state": dict(STATE)}
    out = {"current": CURRENT, "latest": None, "available": False, "notes": "", "published": None,
           "can_install": installable(), "source": not getattr(sys, "frozen", False)}
    try:
        req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "ProvoOremSimulator"})
        with urllib.request.urlopen(req, timeout=10) as r:
            rel = json.loads(r.read())
        asset = next((a for a in rel.get("assets", []) if a.get("name") == ASSET), None)
        latest = re.sub(r"^app-v", "", rel.get("tag_name", ""))
        out.update(latest=latest, notes=(rel.get("body") or "")[:4000], published=rel.get("published_at"),
                   name=rel.get("name"), page=rel.get("html_url"))
        if asset:
            out["asset"] = {"url": asset["browser_download_url"], "size": int(asset.get("size") or 0),
                            "sha256": (asset.get("digest") or "").removeprefix("sha256:") or None}
        out["available"] = bool(asset and CURRENT and _vtuple(latest) > _vtuple(CURRENT))
    except urllib.error.HTTPError as e:
        out["error"] = ("GitHub doesn't show this app's releases to the public (the repository is private), so the app "
                        "can't check for updates." if e.code == 404 else f"GitHub answered {e.code}.")
    except Exception as e:  # noqa: BLE001
        out["error"] = f"Couldn't reach GitHub ({type(e).__name__}). Check your internet connection."
    _cache["check"] = (time.time(), out)
    return {**out, "state": dict(STATE)}


def start_install(data_home: Path) -> dict:
    """Download the latest installer in the background, verify it, run it silently and quit."""
    if not installable():
        return {"ok": False, "error": "Updates install only in the installed Windows app."}
    with _lock:
        if STATE["state"] in ("downloading", "installing"):
            return {"ok": True, "state": dict(STATE)}
        info = check(force=True)
        if not info.get("available"):
            return {"ok": False, "error": info.get("error") or "You already have the latest version."}
        STATE.clear()
        STATE.update(state="downloading", done=0, total=info["asset"]["size"], version=info["latest"])
    threading.Thread(target=_install, args=(info, data_home), daemon=True, name="update").start()
    return {"ok": True, "state": dict(STATE)}


def _install(info: dict, data_home: Path):
    try:
        folder = data_home / "updates"
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.exe"):
            old.unlink(missing_ok=True)
        dest = folder / f"ProvoOremSimulator-Setup-{info['latest']}.exe"
        part = dest.with_suffix(".part")
        h = hashlib.sha256()
        req = urllib.request.Request(info["asset"]["url"], headers={"User-Agent": "ProvoOremSimulator"})
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            while chunk := r.read(1 << 16):
                f.write(chunk)
                h.update(chunk)
                STATE["done"] = STATE.get("done", 0) + len(chunk)
        size, want = part.stat().st_size, info["asset"]
        if want["size"] and size != want["size"]:
            raise RuntimeError(f"the download was incomplete ({size:,} of {want['size']:,} bytes)")
        if want.get("sha256") and h.hexdigest() != want["sha256"]:
            raise RuntimeError("the download didn't match GitHub's checksum")
        part.replace(dest)
        STATE["state"] = "installing"
        flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: outlives this app
        subprocess.Popen([str(dest), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                          f"/LOG={folder / 'install.log'}"], creationflags=flags, close_fds=True)
        print(f"update: running the {info['latest']} installer and quitting")
        sys.stdout.flush()
        time.sleep(1.5)                           # let the page hear that the update has started
        os._exit(0)
    except Exception as e:  # noqa: BLE001
        STATE.clear()
        STATE.update(state="error", error=str(e))
