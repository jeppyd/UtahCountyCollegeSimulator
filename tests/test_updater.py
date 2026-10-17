"""In-app updates: release check, version comparison, and the verified download → silent install → quit sequence
(with GitHub, the installer and the exit stubbed out)."""
import hashlib
import io
import json
import urllib.error

import pytest

from ucsim import updater

PAYLOAD = b"MZ" + b"x" * 5000


def _release(tag="app-v0.1.60", digest=True):
    return {"tag_name": tag, "name": f"Provo-Orem {tag}", "body": "notes", "published_at": "2026-10-17T00:00:00Z",
            "html_url": "https://github.com/x/y/releases/tag/" + tag,
            "assets": [{"name": updater.ASSET, "browser_download_url": "https://example.invalid/setup.exe", "size": len(PAYLOAD),
                        **({"digest": "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()} if digest else {})}]}


@pytest.fixture
def gh(monkeypatch):
    state = {"release": _release(), "payload": PAYLOAD, "status": 200}

    def urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if state["status"] != 200:
            raise urllib.error.HTTPError(url, state["status"], "nope", {}, None)
        body = json.dumps(state["release"]).encode() if "api.github.com" in url else state["payload"]
        return io.BytesIO(body)
    monkeypatch.setattr(updater.urllib.request, "urlopen", urlopen)
    updater._cache.clear()
    updater.STATE.clear()
    updater.STATE["state"] = "idle"
    return state


def test_check_compares_versions_numerically(gh, monkeypatch):
    monkeypatch.setattr(updater, "CURRENT", "0.1.9")
    r = updater.check(force=True)
    assert r["latest"] == "0.1.60" and r["available"]                # 60 > 9 as numbers, not text
    monkeypatch.setattr(updater, "CURRENT", "0.1.60")
    assert not updater.check(force=True)["available"]


def test_private_repo_is_explained(gh, monkeypatch):
    monkeypatch.setattr(updater, "CURRENT", "0.1.1")
    gh["status"] = 404
    r = updater.check(force=True)
    assert not r["available"] and "private" in r["error"]


def test_source_runs_never_install(gh, monkeypatch):
    monkeypatch.setattr(updater, "CURRENT", None)
    assert not updater.check(force=True)["available"]
    assert not updater.start_install(None)["ok"]


@pytest.mark.parametrize("bad", [None, "short", "digest"])
def test_install_verifies_then_runs_the_installer_and_quits(gh, monkeypatch, tmp_path, bad):
    monkeypatch.setattr(updater, "CURRENT", "0.1.5")
    monkeypatch.setattr(updater, "installable", lambda: True)
    ran, quit_ = [], []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda argv, **kw: ran.append(argv))
    monkeypatch.setattr(updater.os, "_exit", lambda code: quit_.append(code))
    monkeypatch.setattr(updater.time, "sleep", lambda s: None)
    if bad == "short":
        gh["payload"] = PAYLOAD[:-10]
    if bad == "digest":
        gh["payload"] = PAYLOAD[:-1] + b"y"
    info = updater.check(force=True)
    updater.STATE.update(state="downloading", done=0)
    updater._install(info, tmp_path)
    if bad is None:
        assert ran and ran[0][1] == "/VERYSILENT" and quit_ == [0]
        assert (tmp_path / "updates" / "ProvoOremSimulator-Setup-0.1.60.exe").read_bytes() == PAYLOAD
    else:
        assert not ran and not quit_ and updater.STATE["state"] == "error"
