"""Desktop launcher: double-click to run the simulator in its own window.

Starts the API + workstation on a free local port, then shows it in a native window (Edge WebView2 via
pywebview). If a native window is not available it opens the default browser plus a small control
window with "Open" and "Quit" buttons. Saved runs and logs go to %LOCALAPPDATA%/ProvoOremSimulator
(or ~/.provo-orem-simulator elsewhere).

    python -m ucsim.app              # what the packaged .exe runs
    python -m ucsim.app --browser    # skip the native window
    python -m ucsim.app --selftest   # start, build a tiny world, step a day, exit 0 on success
"""
from __future__ import annotations

import multiprocessing
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

TITLE = "Provo–Orem Social Simulator"


def data_home() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    home = Path(base) / "ProvoOremSimulator" if base else Path.home() / ".provo-orem-simulator"
    home.mkdir(parents=True, exist_ok=True)
    return home


def free_port(preferred: int = 8765, host: str = "127.0.0.1") -> int:
    """The preferred port if it can be bound, otherwise any free port the OS hands out.
    (Windows reserves some ranges for Hyper-V/WSL, which shows up as 'access forbidden'.)"""
    for port in (preferred, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return s.getsockname()[1]
        except OSError:
            continue
    raise RuntimeError("no free local port")


def start_server(port: int, host: str = "127.0.0.1"):
    import uvicorn

    from ucsim.api.server import app
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning", log_config=None))
    t = threading.Thread(target=server.run, daemon=True, name="api")
    t.start()
    url = f"http://{host}:{port}/"
    for _ in range(300):
        try:
            urllib.request.urlopen(url + "api/status", timeout=1).read()
            return server, url
        except Exception:  # noqa: BLE001 — still starting
            time.sleep(0.1)
    raise RuntimeError("the simulator did not start")


def native_window(url: str, home: Path) -> bool:
    try:
        import webview
    except Exception:  # noqa: BLE001
        return False
    try:
        webview.create_window(TITLE, url, width=1440, height=900, min_size=(1000, 680))
        webview.start(private_mode=False, storage_path=str(home / "webview"))
        return True
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return False


def control_window(url: str):
    """Fallback when no native web view: the browser shows the app; this small window keeps it alive."""
    webbrowser.open(url)
    try:
        import tkinter as tk
    except Exception:  # noqa: BLE001 — no Tk either: keep running until the process is closed
        while True:
            time.sleep(3600)
    root = tk.Tk()
    root.title(TITLE)
    root.resizable(False, False)
    frm = tk.Frame(root, padx=18, pady=14)
    frm.pack()
    tk.Label(frm, text=TITLE, font=("Segoe UI", 12, "bold")).pack(anchor="w")
    tk.Label(frm, text=f"Running in your browser at {url}\nKeep this window open while you use it.", justify="left").pack(anchor="w", pady=(4, 10))
    row = tk.Frame(frm)
    row.pack(anchor="w")
    tk.Button(row, text="Open in browser", command=lambda: webbrowser.open(url)).pack(side="left")
    tk.Button(row, text="Quit", command=root.destroy).pack(side="left", padx=8)
    root.mainloop()


def selftest(url: str) -> int:
    import json

    def call(path, body=None):
        req = urllib.request.Request(url + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
        return json.loads(urllib.request.urlopen(req, timeout=60).read() or b"{}")

    assert call("api/registry")["variables"], "registry"
    call("api/world", {"scale": 0.02, "seed": 3, "warmup": 2})
    for _ in range(600):
        st = call("api/status")
        if st.get("has_world") and st["job"].get("state") == "idle":
            break
        assert st["job"].get("state") != "error", st["job"]
        time.sleep(0.2)
    assert st.get("has_world"), "world was not built"
    call("api/step", {"days": 1})
    for _ in range(600):
        st = call("api/status")
        if st["job"].get("state") == "idle":
            break
        time.sleep(0.2)
    assert st["day"] >= 3, st
    # the game layer: pulse, field summaries, a What-if and the butterfly views
    assert call("api/pulse")["present"] > 0, "pulse"
    assert call("api/fields/summary")["fields"], "field summary"
    call("api/fork", {"interventions": [{"preset": "rent_up_20"}]})
    call("api/step", {"days": 1})
    for _ in range(600):
        if call("api/status")["job"].get("state") == "idle":
            break
        time.sleep(0.2)
    assert call("api/compare/fields")["fields"], "compare fields"
    assert "people" in call("api/compare/people?k=5"), "compare people"
    if getattr(sys, "frozen", False):
        assert call("api/update/check").get("current"), "the build has no version stamp, so it could never offer updates"
        # the What-if lookup tools must start from the packaged .exe, as Claude Code and Codex will start them
        from ucsim.llm import backends, compiler
        # (reported, not fatal: without them What-ifs still work, the plan is just checked afterwards)
        try:
            tools = backends.probe_tool_server(compiler.tool_server("selftest", url.rstrip("/")))
            print(f"selftest tool server: ok {tools}")
        except Exception as e:  # noqa: BLE001
            print(f"selftest tool server: FAILED {e!r}")
    page = urllib.request.urlopen(url, timeout=10).read().decode("utf-8", "replace")
    assert "<div id=\"root\">" in page, "workstation page missing"
    urllib.request.urlopen(url + "geo/roads.json", timeout=10).read()
    # Monte Carlo spawns worker processes — the classic failure point for packaged apps
    call("api/montecarlo", {"seeds": 1, "days": 2, "scale": 0.02, "workers": 2,
                            "scenarios": {"rent_up_20": [{"preset": "rent_up_20"}]}})
    for _ in range(900):
        mc = call("api/montecarlo")
        if mc.get("state") in ("done", "error"):
            break
        time.sleep(0.2)
    assert mc.get("state") == "done", mc
    print(f"selftest ok: day {st['day']}, {st['present']} people, Monte Carlo {mc['runs']} runs")
    return 0


def main():
    multiprocessing.freeze_support()  # Monte Carlo workers re-enter here in the packaged app
    if "--mcp-server" in sys.argv[1:]:
        # Claude Code / Codex start the app's own .exe as the What-if lookup tools (MCP over stdio); the installed
        # app has no separate Python to run `python -m ucsim.llm.mcp_server`
        from ucsim.llm.mcp_server import mcp
        mcp.run()
        return
    home = data_home()
    os.environ.setdefault("UCSIM_RUNS", str(home / "runs"))
    if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
        log = open(home / "simulator.log", "a", encoding="utf-8", buffering=1)  # windowed app: no console
        sys.stdout = sys.stderr = log
    print(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} starting {TITLE}")
    from ucsim.telemetry import LOG, setup_logging
    setup_logging(home / "logs")
    LOG.info("Started %s", TITLE)
    args = set(sys.argv[1:])
    port = free_port()
    try:
        server, url = start_server(port)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
    print(f"serving {url}")
    if "--selftest" in args:
        try:
            code = selftest(url)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            code = 1
        server.should_exit = True
        sys.stdout.flush()
        os._exit(code)
    if "--browser" in args or not native_window(url, home):
        control_window(url)
    server.should_exit = True
    os._exit(0)


if __name__ == "__main__":
    main()
