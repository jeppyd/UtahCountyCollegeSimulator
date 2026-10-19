"""Ways to reach a model without an API key.

* `claude`  — Claude Code in headless mode (`claude -p`), signed in with a Claude Pro/Max subscription. Streams its
  steps, loads the guide + catalog as an appended system prompt, uses the simulator's own tools over MCP, and returns
  the plan as schema-checked JSON.
* `codex`   — OpenAI Codex CLI (`codex exec`), signed in with ChatGPT Plus. Reads the guide + catalog from AGENTS.md.
* `openai`  — any OpenAI-compatible local server (LM Studio, Ollama): a small tool loop, then a schema-constrained answer.
* `anthropic` — the Claude API with an API key (pay as you go, no install): the official SDK, the same tool loop, then
  a structured-output answer.
* `openai_api` — the OpenAI API with an API key (pay as you go, no install): `openai`'s loop against api.openai.com.

Every backend returns {"plan": dict|None, "text": str, "error": str|None, "meta": {...}} and reports progress through
`on_step(kind, text)`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_NAMES = ("search_entities", "describe_entity", "count_people", "validate_plan")
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._:\[\]-]{1,64}$")     # model names: never anything a shell could interpret
EFFORTS = ("low", "medium", "high", "xhigh", "max")
_help_cache: dict[str, str] = {}


WINDOWS = os.name == "nt"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if WINDOWS else 0
_version_cache: dict[str, tuple[float, str | None]] = {}


def _usual_places(cmd: str) -> list[Path]:
    """Where installers put the CLIs, for when PATH is stale (the app was started before the install)."""
    home = Path.home()
    if WINDOWS:
        appdata, local = Path(os.environ.get("APPDATA", home / "AppData/Roaming")), Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        return [home / ".local/bin" / f"{cmd}.exe", appdata / "npm" / f"{cmd}.cmd", local / "Programs" / cmd / f"{cmd}.exe",
                Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "nodejs" / f"{cmd}.cmd"]
    return [home / ".local/bin" / cmd, home / ".claude/local" / cmd, home / ".npm-global/bin" / cmd,
            Path("/opt/homebrew/bin") / cmd, Path("/usr/local/bin") / cmd]


def which(cmd: str) -> str | None:
    hit = shutil.which(cmd)
    if hit or os.sep in cmd or "/" in cmd:
        return hit
    return next((str(c) for c in _usual_places(cmd) if c.is_file()), None)


def resolve_cli(name: str, override: str | None = None) -> tuple[list[str] | None, str | None]:
    """The argv prefix that launches a CLI. npm's Windows launchers (claude.cmd, codex.cmd) run through cmd.exe, which
    mangles JSON arguments and can execute text in them, so they are resolved to `node <script.js>` instead."""
    exe = which(override or name)
    if not exe:
        return None, None
    if WINDOWS and exe.lower().endswith((".cmd", ".bat")):
        try:
            text = Path(exe).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        m = re.search(r'%~?dp0%?\\?([^"%\r\n]+?\.(?:c?js|mjs))', text)
        base = Path(exe).parent
        if m:
            script = (base / m.group(1).lstrip("\\/")).resolve()
            node = base / "node.exe"
            node = str(node) if node.exists() else which("node")
            if script.exists() and node:
                return [node, str(script)], None
        native = base / f"{name}.exe"
        if native.exists():
            return [str(native)], None
        return None, (f"Found {Path(exe).name}, an npm launcher that can't be run safely from the simulator. Install "
                      f"{'Claude Code with its native installer' if name == 'claude' else name + ' so that ' + name + '.exe is on PATH'}, "
                      f"or set the path to the real program in settings.")
    return [exe], None


def _spawn(argv: list[str], **kw) -> subprocess.Popen:
    """Start a CLI in its own process group (so Stop can end it and anything it starts), without a console window."""
    if WINDOWS:
        kw["creationflags"] = kw.get("creationflags", 0) | subprocess.CREATE_NEW_PROCESS_GROUP | _NO_WINDOW
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(argv, **kw)


def _kill_tree(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    try:
        if WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=10, creationflags=_NO_WINDOW)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass


def _run_quick(argv: list[str], timeout: float = 20) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                              encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
    except Exception:  # noqa: BLE001
        return None


def _help(argv: list[str]) -> str:
    key = " ".join(argv)
    if key not in _help_cache:
        out = _run_quick([*argv, "--help"])
        _help_cache[key] = out.stdout if out else ""
    return _help_cache[key]


def version(cmd: str, override: str | None = None, fresh: bool = False) -> str | None:
    """Installed version (cached for a minute: the status panel asks often)."""
    hit = _version_cache.get(cmd)
    if hit and time.time() - hit[0] < 60 and not fresh:
        return hit[1]
    argv, err = resolve_cli(cmd, override)
    v = None
    if argv:
        out = _run_quick([*argv, "--version"])
        txt = ((out.stdout or out.stderr) if out else "").strip()
        v = txt.splitlines()[0] if txt else "installed"
    elif err:
        v = None
    _version_cache[cmd] = (time.time(), v)
    return v


def _child_env(drop_api_key: bool) -> dict:
    env = dict(os.environ)
    if drop_api_key:
        # an API key in the environment would make Claude Code bill the key instead of the subscription
        env.pop("ANTHROPIC_API_KEY", None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _describe_tool(name: str, inp) -> str:
    inp = inp if isinstance(inp, dict) else {}
    short = str(name).split("__")[-1]
    if short == "Read":
        return f"Reading {Path(str(inp.get('file_path', ''))).name}"
    if short in ("Grep", "Glob"):
        return f"Searching the catalog for “{inp.get('pattern', '')}”"
    if short == "search_entities":
        return f"Looking up “{inp.get('query', '')}”"
    if short == "describe_entity":
        return f"Checking {inp.get('ref', 'a place')}"
    if short == "count_people":
        return "Counting who would be affected"
    if short == "validate_plan":
        plan = inp.get("plan")
        if isinstance(plan, str):
            try:
                plan = json.loads(plan)
            except json.JSONDecodeError:
                plan = None
        n = len(plan.get("changes") or []) if isinstance(plan, dict) else 0
        return f"Checking a draft plan ({n} change{'s' if n != 1 else ''})"
    if short == "StructuredOutput":
        return "Writing up the plan"
    return f"Using {short}"


class Cancelled(Exception):
    pass


def _feed_stdin(proc: subprocess.Popen, text: str):
    """Write the prompt without blocking the reader (a CLI that exits early must not hide its own error)."""
    def go():
        try:
            proc.stdin.write(text)
            proc.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass
    threading.Thread(target=go, daemon=True).start()


def _pump(proc: subprocess.Popen, cancel: threading.Event, timeout: float, on_line):
    """Read stdout lines until EOF, cancellation or timeout. The process (and anything it started) is killed on cancel,
    on timeout and on any unexpected error, so nothing is left running."""
    t0 = time.time()
    done = threading.Event()

    def watchdog():
        while not done.wait(0.25):
            if cancel.is_set() or time.time() - t0 > timeout:
                _kill_tree(proc)
                try:
                    proc.stdout.close()
                except Exception:  # noqa: BLE001
                    pass
                return
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        for line in proc.stdout:
            try:
                on_line(line)
            except Exception:  # noqa: BLE001 — one odd event must not orphan the process
                traceback.print_exc()
    except (ValueError, OSError):
        pass    # stdout closed by the watchdog
    finally:
        done.set()
        if proc.poll() is None and (cancel.is_set() or time.time() - t0 > timeout):
            _kill_tree(proc)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
    if cancel.is_set():
        raise Cancelled()
    if time.time() - t0 > timeout:
        raise TimeoutError(f"no answer within {int(timeout)} s")


# ---------------------------------------------------------------------- Claude Code
def run_claude(prompt: str, schema: dict, pack: Path, settings: dict, on_step, cancel: threading.Event, mcp_config: Path | None) -> dict:
    argv, why = resolve_cli("claude", settings.get("claude_path") or None)
    if not argv:
        return {"plan": None, "text": "", "error": why or "Claude Code isn't installed or isn't on PATH (install it and run `claude` once to sign in).", "meta": {}}
    h = _help(argv)
    cmd = [*argv, "-p", "--output-format", "stream-json", "--verbose", "--json-schema", json.dumps(schema, separators=(",", ":"))]
    sysfile = pack / "system.md"
    # the -file form is hidden from --help in current versions ("--append-system-prompt[-file]"); the guide + catalog
    # (~80 KB) must never go on the command line (Windows caps it at 32 KB)
    if "system-prompt-file" in h or "system-prompt[-file]" in h or not h:
        cmd += ["--append-system-prompt-file", str(sysfile)]
    elif not WINDOWS:
        cmd += ["--append-system-prompt", sysfile.read_text(encoding="utf-8")]
    else:
        return {"plan": None, "text": "", "error": "This Claude Code version is too old for the simulator: update it (`claude update`).", "meta": {}}
    allowed = ["Read", "Grep", "Glob"]
    if mcp_config is not None:
        cmd += ["--mcp-config", str(mcp_config), "--strict-mcp-config"]
        allowed += [f"mcp__ucsim__{t}" for t in TOOL_NAMES]
    cmd += ["--tools", "Read,Grep,Glob", "--allowedTools", ",".join(allowed), "--permission-mode", "dontAsk",
            "--max-turns", str(int(settings.get("max_turns", 40))), "--add-dir", str(ROOT / "docs")]
    if "--no-session-persistence" in h:
        cmd.append("--no-session-persistence")
    if settings.get("claude_model") and SAFE_TOKEN.match(str(settings["claude_model"])):
        cmd += ["--model", settings["claude_model"]]
    if settings.get("claude_effort") in EFFORTS and "--effort" in h:
        cmd += ["--effort", settings["claude_effort"]]
    if "--restricted" in h:
        cmd.append("--restricted")
    try:
        proc = _spawn(cmd, cwd=str(pack), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      text=True, encoding="utf-8", errors="replace", env=_child_env(settings.get("use_subscription", True)), bufsize=1)
    except OSError as e:
        return {"plan": None, "text": "", "error": f"Couldn't start Claude Code: {e}", "meta": {}}
    err_lines: list[str] = []
    threading.Thread(target=lambda: err_lines.extend(proc.stderr.readlines()), daemon=True).start()
    _feed_stdin(proc, prompt)
    final: dict = {}
    notes: list[str] = []

    def on_line(line: str):
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            return
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            on_step("start", f"Claude is reading the catalog ({d.get('model', 'default model')})")
        elif t == "assistant":
            for b in d.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    on_step("tool", _describe_tool(b.get("name", ""), b.get("input") or {}))
                elif b.get("type") == "text" and b.get("text", "").strip():
                    notes.append(b["text"].strip())
                    on_step("note", b["text"].strip()[:400])
                elif b.get("type") == "thinking" and (b.get("thinking") or "").strip():
                    on_step("think", b["thinking"].strip()[:400])
        elif t == "result":
            final.update(d)
    try:
        _pump(proc, cancel, float(settings.get("timeout", 600)), on_line)
    except Cancelled:
        return {"plan": None, "text": "", "error": "cancelled", "meta": {}}
    except TimeoutError as e:
        return {"plan": None, "text": "\n".join(notes), "error": str(e), "meta": {}}
    meta = {k: final.get(k) for k in ("num_turns", "duration_ms", "session_id", "subtype", "stop_reason", "terminal_reason")}
    meta["model"] = next(iter((final.get("modelUsage") or {}).keys()), None)
    if not final:
        tail = "".join(err_lines[-12:]).strip()
        hint = " (is Claude Code signed in? run `claude` once in a terminal)" if "login" in tail.lower() or "auth" in tail.lower() or not tail else ""
        return {"plan": None, "text": "\n".join(notes), "error": f"Claude Code ended without an answer{hint}. {tail[-600:]}", "meta": meta}
    plan = final.get("structured_output")
    if plan is None and isinstance(final.get("result"), str):
        plan = _json_from_text(final["result"])
    err = None
    if final.get("is_error") or plan is None:
        err = f"Claude Code: {final.get('subtype') or 'error'} — {str(final.get('result') or '')[:500]}"
    return {"plan": plan, "text": "\n".join(notes), "error": err if plan is None else None, "meta": meta}


def _json_from_text(s: str):
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(s[i:j + 1])
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------- Codex CLI
def _toml(v) -> str:
    """A value for `codex -c key=value` (parsed as TOML): JSON strings and arrays are valid TOML; tables go inline."""
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}={json.dumps(str(x))}" for k, x in v.items()) + "}"
    return json.dumps(v)


def codex_tool_args(server: dict | None) -> list[str]:
    """`-c` overrides that give Codex the simulator's lookup tools for this run only (nothing is written to the
    user's ~/.codex/config.toml). Read-only tools, approved without asking; Codex carries on without them if the
    server can't start."""
    if not server:
        return []
    keys = {"command": server["command"], "args": server["args"], "env": server["env"], "required": False,
            "startup_timeout_sec": 30, "tool_timeout_sec": 90, "default_tools_approval_mode": "approve"}
    out = []
    for k, v in keys.items():
        out += ["-c", f"mcp_servers.ucsim.{k}={_toml(v)}"]
    return out


def run_codex(prompt: str, schema: dict, pack: Path, settings: dict, on_step, cancel: threading.Event,
              tool_server: dict | None = None) -> dict:
    argv, why = resolve_cli("codex", settings.get("codex_path") or None)
    if not argv:
        return {"plan": None, "text": "", "error": why or "Codex CLI isn't installed or isn't on PATH (install it and run `codex login`).", "meta": {}}
    import uuid
    tag = uuid.uuid4().hex[:10]
    schema_file = pack / f"codex_schema_{tag}.json"       # per job: concurrent compiles never share a file
    out_file = pack / f"codex_last_{tag}.txt"
    try:
        schema_file.write_text(json.dumps(schema), encoding="utf-8")
        cmd = [*argv, "exec", "--json", "--output-schema", str(schema_file), "-o", str(out_file), "--sandbox", "read-only",
               "--skip-git-repo-check", "-C", str(pack), *codex_tool_args(tool_server)]
        if settings.get("codex_model") and SAFE_TOKEN.match(str(settings["codex_model"])):
            cmd += ["-m", settings["codex_model"]]
        if settings.get("codex_effort") in CODEX_EFFORTS:
            cmd += ["-c", f'model_reasoning_effort="{settings["codex_effort"]}"']
        cmd.append("-")
        try:
            proc = _spawn(cmd, cwd=str(pack), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace", env=_child_env(False), bufsize=1)
        except OSError as e:
            return {"plan": None, "text": "", "error": f"Couldn't start Codex: {e}", "meta": {}}
        _feed_stdin(proc, prompt)
        return _codex_read(proc, out_file, settings, on_step, cancel)
    finally:
        schema_file.unlink(missing_ok=True)
        out_file.unlink(missing_ok=True)


def _codex_read(proc, out_file: Path, settings: dict, on_step, cancel: threading.Event) -> dict:
    tail: list[str] = []

    def on_line(line: str):
        tail.append(line)
        del tail[:-20]
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            return
        item = d.get("item") or d.get("msg") or {}
        item = item if isinstance(item, dict) else {}
        typ = item.get("type") or d.get("type", "")
        if typ == "mcp_tool_call":
            if d.get("type") == "item.started":
                on_step("tool", {"search_entities": "Looking something up", "describe_entity": "Reading about it",
                                 "count_people": "Counting people", "validate_plan": "Checking the draft"}.get(item.get("tool"), f"Using {item.get('tool')}"))
            elif item.get("error"):
                on_step("note", f"A lookup failed: {str((item.get('error') or {}).get('message', ''))[:200]}")
        elif "command" in str(typ):
            on_step("tool", f"Reading: {str(item.get('command', ''))[:120]}")
        elif "reasoning" in str(typ) and item.get("text"):
            on_step("think", str(item["text"])[:400])
        elif "agent_message" in str(typ) and item.get("text"):
            on_step("note", str(item["text"])[:400])
        elif d.get("type") == "thread.started":
            on_step("start", "Codex is reading the catalog")
    try:
        _pump(proc, cancel, float(settings.get("timeout", 600)), on_line)
    except Cancelled:
        return {"plan": None, "text": "", "error": "cancelled", "meta": {}}
    except TimeoutError as e:
        return {"plan": None, "text": "", "error": str(e), "meta": {}}
    text = out_file.read_text(encoding="utf-8") if out_file.exists() else ""
    plan = _json_from_text(text)
    if plan is None:
        return {"plan": None, "text": text, "error": "Codex ended without a plan. " + "".join(tail)[-600:], "meta": {}}
    from .plan import unstrict
    return {"plan": unstrict(plan), "text": "", "error": None, "meta": {"backend": "codex"}}


# ---------------------------------------------------------------------- OpenAI-compatible (LM Studio, Ollama)
def _post(url: str, body: dict, key: str, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key or 'local'}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get_json(url: str, timeout: float = 3):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=timeout) as r:
        return json.loads(r.read().decode())


# The local model reads the compact guide and catalog (~12k tokens) plus tool results and writes the plan.
MIN_CONTEXT = 16384


def _lms_root(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


def local_models(base_url: str, key: str = "") -> list[dict]:
    """Chat models a local server offers, loaded ones first:
    [{id, loaded, context, max_context, instances, params, size_gb, tools}].
    LM Studio's own API (v1 since 0.4, else v0) says which models are downloaded vs loaded, with what context window,
    and hides embedding models; any other OpenAI-compatible server (Ollama…) just lists ids."""
    base = base_url.rstrip("/")
    root = _lms_root(base)
    hdr = {"Accept": "application/json", "Authorization": f"Bearer {key or 'lm-studio'}"}

    def get(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=3) as r:
            return json.loads(r.read().decode())
    try:                                   # LM Studio ≥ 0.4
        out = []
        for m in get(root + "/api/v1/models").get("models", []):
            if m.get("type", "llm") != "llm" or not m.get("key"):
                continue
            inst = m.get("loaded_instances") or []
            out.append({"id": m["key"], "loaded": bool(inst), "instances": [i.get("id") for i in inst if i.get("id")],
                        "context": ((inst[0].get("config") or {}).get("context_length") if inst else None),
                        "max_context": m.get("max_context_length"), "params": m.get("params_string"),
                        "size_gb": round(m["size_bytes"] / 1e9, 1) if m.get("size_bytes") else None,
                        "tools": (m.get("capabilities") or {}).get("trained_for_tool_use"), "name": m.get("display_name")})
        if out:
            return sorted(out, key=lambda m: not m["loaded"])
    except Exception:  # noqa: BLE001
        pass
    try:                                   # older LM Studio
        rows = get(root + "/api/v0/models").get("data", [])
        out = [{"id": m.get("id"), "loaded": m.get("state") == "loaded", "instances": [m.get("id")] if m.get("state") == "loaded" else [],
                "context": m.get("loaded_context_length"), "max_context": m.get("max_context_length")}
               for m in rows if m.get("id") and m.get("type", "llm") in ("llm", "vlm")]
        if out:
            return sorted(out, key=lambda m: not m["loaded"])
    except Exception:  # noqa: BLE001
        pass
    try:
        rows = get(base + "/models").get("data", [])
    except Exception:  # noqa: BLE001
        return []
    return [{"id": m["id"], "loaded": None, "instances": []} for m in rows if m.get("id") and "embed" not in m["id"].lower()]


def load_local_model(base_url: str, model: str, context_length: int = 32768, unload_others: bool = True, key: str = "") -> dict:
    """Load a model into LM Studio (its v1 REST API, LM Studio 0.4+) with a context window big enough for the
    simulator's instructions; optionally unload whatever else is loaded first, so they don't share the GPU."""
    root = _lms_root(base_url)
    models = local_models(base_url, key)
    target = next((m for m in models if m["id"] == model), None)
    if target is None:
        return {"ok": False, "error": f"LM Studio doesn't list a model called {model}."}
    if target.get("max_context"):
        context_length = min(int(context_length), int(target["max_context"]))
    unloaded = []
    for m in models:
        for inst in m.get("instances") or []:
            if unload_others or m["id"] == model:      # the target too, so it comes back with the new context window
                try:
                    _post(root + "/api/v1/models/unload", {"instance_id": inst}, key, 60)
                    unloaded.append(inst)
                except Exception:  # noqa: BLE001
                    pass
    try:
        r = _post(root + "/api/v1/models/load", {"model": model, "context_length": int(context_length), "echo_load_config": True}, key, 900)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"ok": False, "error": "This LM Studio is too old to load models on request (it needs version 0.4 or newer). "
                                          "Update LM Studio, or load the model in LM Studio's Developer tab."}
        return {"ok": False, "error": f"LM Studio refused: {e.read().decode(errors='replace')[:300] or e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Couldn't load the model: {e}"}
    cfg = r.get("load_config") or {}
    return {"ok": True, "model": model, "instance": r.get("instance_id"), "seconds": r.get("load_time_seconds"),
            "context": cfg.get("context_length", context_length), "unloaded": unloaded}


# reasoning levels the simulator offers for Codex (the catalog also has "ultra", which delegates to sub-agents)
CODEX_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")
_codex_models_cache: dict = {}


def codex_models(override: str | None = None) -> list[dict]:
    """The models Codex offers (its own catalog: `codex debug models`, no sign-in needed), in Codex's order, with each
    model's reasoning levels: [{slug, name, default_effort, efforts}]. Cached for 10 minutes."""
    hit = _codex_models_cache.get(override)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    argv, _ = resolve_cli("codex", override)
    out = []
    if argv:
        res = _run_quick([*argv, "debug", "models"], timeout=30)
        try:
            rows = json.loads(res.stdout).get("models", []) if res and res.stdout else []
        except (json.JSONDecodeError, AttributeError):
            rows = []
        for m in sorted((m for m in rows if isinstance(m, dict) and m.get("visibility", "list") == "list" and m.get("slug")),
                        key=lambda m: m.get("priority", 999)):
            efforts = [e.get("effort") for e in m.get("supported_reasoning_levels") or [] if e.get("effort") in CODEX_EFFORTS]
            out.append({"slug": m["slug"], "name": m.get("display_name") or m["slug"], "default_effort": m.get("default_reasoning_level"),
                        "efforts": efforts, "description": (m.get("description") or "")[:160]})
    _codex_models_cache[override] = (time.time(), out)
    return out


def openai_models(base_url: str, key: str = "") -> list[str]:
    return [m["id"] for m in local_models(base_url, key)]


OPENAI_TOOLS = [
    {"type": "function", "function": {"name": "search_entities", "description": "Find people, places, groups or model concepts by name; returns exact refs and ready-made `who` filters.",
                                      "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "kinds": {"type": "array", "items": {"type": "string"}}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "describe_entity", "description": "Details of one entity by ref, e.g. complex:587, ward:12, person:4031.",
                                      "parameters": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]}}},
    {"type": "function", "function": {"name": "count_people", "description": "Count how many people a `who` filter selects right now.",
                                      "parameters": {"type": "object", "properties": {"who": {"type": "object"}}, "required": ["who"]}}},
    {"type": "function", "function": {"name": "validate_plan", "description": "Check a draft plan; returns errors to fix and warnings.",
                                      "parameters": {"type": "object", "properties": {"plan": {"type": "object"}}, "required": ["plan"]}}},
]


def run_openai(system: str, prompt: str, schema: dict, settings: dict, on_step, cancel: threading.Event, tool_fn) -> dict:
    base = (settings.get("openai_url") or "http://localhost:1234/v1").rstrip("/")
    key = settings.get("openai_key") or "lm-studio"
    model = settings.get("openai_model") or (openai_models(base, key) or [""])[0]
    hosted = "api.openai.com" in base          # OpenAI's own API: reasoning models only take the default temperature
    temp = (lambda t: {}) if hosted else (lambda t: {"temperature": t})
    if not model:
        return {"plan": None, "text": "", "error": f"No model is loaded at {base} (start LM Studio's server and load a model).", "meta": {}}
    deadline = time.time() + float(settings.get("timeout", 600))     # one budget for the whole conversation

    def left() -> float:
        rest = deadline - time.time()
        if rest <= 0:
            raise TimeoutError(f"no answer within {int(float(settings.get('timeout', 600)))} s")
        return rest
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    on_step("start", f"Asking {model} at {base}")
    try:
        for _ in range(int(settings.get("openai_tool_rounds", 6)) if tool_fn is not None else 0):
            if cancel.is_set():
                return {"plan": None, "text": "", "error": "cancelled", "meta": {}}
            r = _post(base + "/chat/completions", {"model": model, "messages": msgs, "tools": OPENAI_TOOLS, **temp(0.3)}, key, left())
            m = r["choices"][0]["message"]
            calls = m.get("tool_calls") or []
            if not calls:
                if m.get("content"):
                    on_step("note", str(m["content"])[:400])
                break
            msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
            for c in calls:
                fn = c.get("function", {})
                args = fn.get("arguments")
                try:
                    args = json.loads(args) if isinstance(args, str) else (args or {})
                except json.JSONDecodeError:
                    args = {}
                on_step("tool", _describe_tool(fn.get("name", ""), args))
                try:
                    res = tool_fn(fn.get("name", ""), args if isinstance(args, dict) else {})
                except Exception as e:  # noqa: BLE001 — a bad tool call goes back to the model, it doesn't end the compile
                    res = {"error": f"{type(e).__name__}: {e}"}
                msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": json.dumps(res)[:6000]})
        if cancel.is_set():
            return {"plan": None, "text": "", "error": "cancelled", "meta": {}}
        msgs.append({"role": "user", "content": "Now give the final plan as JSON matching the schema."})
        on_step("tool", "Writing up the plan")
        r = _post(base + "/chat/completions", {"model": model, "messages": msgs, **temp(0.2),
                                               "response_format": {"type": "json_schema", "json_schema": {"name": "whatif_plan", "strict": True, "schema": schema}}},
                  key, left())
        txt = r["choices"][0]["message"].get("content") or ""
    except TimeoutError as e:
        return {"plan": None, "text": "", "error": str(e), "meta": {}}
    except urllib.error.HTTPError as e:
        return {"plan": None, "text": "", "error": _http_words(e, "OpenAI" if hosted else "Local model"), "meta": {}}
    except urllib.error.URLError as e:
        return {"plan": None, "text": "", "error": f"Couldn't reach {base}: {e}", "meta": {}}
    except Exception as e:  # noqa: BLE001
        return {"plan": None, "text": "", "error": _http_words(e, "OpenAI" if hosted else "Local model"), "meta": {}}
    plan = _json_from_text(txt)
    if plan is None:
        return {"plan": None, "text": txt, "error": f"{'The model' if hosted else 'The local model'} didn't return a valid plan.", "meta": {"model": model}}
    from .plan import unstrict
    return {"plan": unstrict(plan), "text": "", "error": None, "meta": {"model": model, "backend": "openai"}}


def _http_words(e: Exception, who: str) -> str:
    """An HTTP failure from a hosted API in plain words (a wrong key, no credit, too many requests)."""
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    body = ""
    try:
        body = e.read().decode()[:300] if hasattr(e, "read") else str(getattr(e, "message", "") or "")
    except Exception:  # noqa: BLE001
        pass
    if code == 401:
        return f"{who} didn't accept the API key (check that it was copied in full)."
    if code == 403:
        return f"{who} refused the request: the key may lack access to this model. {body}".strip()
    if code == 404:
        return f"{who} doesn't know that model name. Pick another model. {body}".strip()
    if code == 429:
        return f"{who} says too many requests, or the account is out of credit. Check your billing page, wait a minute, and try again."
    if code in (400, 402) and re.search(r"credit|billing|quota|balance", body, re.I):
        return f"{who} says the account has no credit left. Add credit on the billing page and try again."
    return f"{who} error{f' ({code})' if code else ''}: {body or repr(e)}"


# ---------------------------------------------------------------------- the Claude API (an API key)
ANTHROPIC_MODELS = [("claude-opus-5-5", "Claude Opus 5.5 (most careful)"), ("claude-sonnet-5-5", "Claude Sonnet 5.5 (faster, cheaper)"),
                    ("claude-haiku-5-5", "Claude Haiku 5.5 (quickest, cheapest)")]
ANTHROPIC_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def _anthropic_tools() -> list[dict]:
    return [{"name": t["function"]["name"], "description": t["function"]["description"], "input_schema": t["function"]["parameters"]}
            for t in OPENAI_TOOLS]


def _anthropic_client(key: str, timeout: float):
    import anthropic
    return anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=2)


def _anthropic_error(e: Exception) -> str:
    import anthropic
    if isinstance(e, anthropic.AuthenticationError):
        return "Claude didn't accept the API key (check that it was copied in full)."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "This API key can't use that model; pick another model or check the key's workspace."
    if isinstance(e, anthropic.NotFoundError):
        return "Claude doesn't know that model name; pick another model."
    if isinstance(e, anthropic.RateLimitError):
        return "Claude says too many requests right now; wait a minute and try again."
    if isinstance(e, anthropic.BadRequestError) and re.search(r"credit|billing|balance", str(e), re.I):
        return "The Claude account has no API credit left. Add credit at console.anthropic.com (Billing) and try again."
    if isinstance(e, anthropic.APIConnectionError):
        return "Couldn't reach the Claude API: check the internet connection."
    if isinstance(e, anthropic.APIStatusError):
        return f"Claude API error ({e.status_code}): {getattr(e, 'message', e)}"
    return f"Claude API error: {e!r}"


def _anthropic_call(client, **kw):
    """One request, with server-side refusal fallback (the API re-runs a declined request on a suitable model)."""
    return client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)


def run_anthropic(system: str, prompt: str, schema: dict, settings: dict, on_step, cancel: threading.Event, tool_fn) -> dict:
    key = settings.get("anthropic_key") or ""
    if not key:
        return {"plan": None, "text": "", "error": "Paste your Claude API key in the AI setup first.", "meta": {}}
    model = settings.get("anthropic_model") or ANTHROPIC_MODELS[0][0]
    effort = settings.get("anthropic_effort") or "medium"
    deadline = time.time() + float(settings.get("timeout", 600))
    try:
        client = _anthropic_client(key, float(settings.get("timeout", 600)))
    except ImportError:
        return {"plan": None, "text": "", "error": "The `anthropic` package is missing (pip install anthropic).", "meta": {}}
    # the guide and catalog are the same every time: cache them
    sys_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    common = {"model": model, "max_tokens": 16000, "system": sys_blocks, "output_config": {"effort": effort}}
    msgs: list = [{"role": "user", "content": prompt}]
    on_step("start", f"Asking {model} (Claude API)")
    try:
        if tool_fn is not None:
            for _ in range(int(settings.get("anthropic_tool_rounds", 8))):
                if cancel.is_set():
                    return {"plan": None, "text": "", "error": "cancelled", "meta": {}}
                if time.time() > deadline:
                    raise TimeoutError(f"no answer within {int(float(settings.get('timeout', 600)))} s")
                r = _anthropic_call(client, messages=msgs, tools=_anthropic_tools(), **common)
                if r.stop_reason == "refusal":
                    return {"plan": None, "text": "", "error": "Claude declined this request.", "meta": {"model": model}}
                msgs.append({"role": "assistant", "content": r.content})
                calls = [b for b in r.content if b.type == "tool_use"]
                if r.stop_reason != "tool_use" or not calls:
                    break
                results = []
                for c in calls:
                    on_step("tool", _describe_tool(c.name, c.input))
                    try:
                        res = tool_fn(c.name, c.input if isinstance(c.input, dict) else {})
                    except Exception as e:  # noqa: BLE001 — a bad tool call goes back to the model
                        res = {"error": f"{type(e).__name__}: {e}"}
                    results.append({"type": "tool_result", "tool_use_id": c.id, "content": json.dumps(res)[:6000]})
                msgs.append({"role": "user", "content": results})
        if cancel.is_set():
            return {"plan": None, "text": "", "error": "cancelled", "meta": {}}
        final = "Now give the final plan as JSON matching the schema."
        if msgs[-1]["role"] == "assistant":
            msgs.append({"role": "user", "content": final})
        elif isinstance(msgs[-1]["content"], list):       # the tool rounds ran out right after tool results
            msgs[-1]["content"].append({"type": "text", "text": final})
        on_step("tool", "Writing up the plan")
        extra = {"tools": _anthropic_tools(), "tool_choice": {"type": "none"}} if tool_fn is not None else {}
        r = _anthropic_call(client, messages=msgs, **extra,
                            **{**common, "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}}})
        if r.stop_reason == "refusal":
            return {"plan": None, "text": "", "error": "Claude declined this request.", "meta": {"model": model}}
        txt = "".join(b.text for b in r.content if b.type == "text")
    except TimeoutError as e:
        return {"plan": None, "text": "", "error": str(e), "meta": {}}
    except Exception as e:  # noqa: BLE001
        return {"plan": None, "text": "", "error": _anthropic_error(e), "meta": {}}
    plan = _json_from_text(txt)
    if plan is None:
        return {"plan": None, "text": txt, "error": "Claude didn't return a valid plan.", "meta": {"model": model}}
    from .plan import unstrict
    return {"plan": unstrict(plan), "text": "", "error": None, "meta": {"model": model, "backend": "anthropic"}}


# ---------------------------------------------------------------------- "is it really working?" (a one-word round trip)
SIGNED_OUT = re.compile(r"log ?in|sign ?in|authenticat|unauthori[sz]ed|credential|api key|not logged|/login|expired", re.I)


def test_connection(backend: str, settings: dict, timeout: float = 90) -> dict:
    """Ask the chosen model to reply with one word. {ok, reply, seconds, error, hint} — the hint says what to do next."""
    t0 = time.time()
    ask = "Reply with exactly one word: ready"

    def out(ok, reply="", error="", hint=""):
        return {"ok": ok, "reply": reply[:200], "error": error[:600], "hint": hint, "seconds": round(time.time() - t0, 1), "backend": backend}
    try:
        if backend in ("claude", "codex"):
            argv, why = resolve_cli(backend, settings.get(f"{backend}_path") or None)
            if not argv:
                return out(False, error=why or f"{'Claude Code' if backend == 'claude' else 'Codex'} isn't installed yet.",
                           hint="Do the install step, then test again.")
            if backend == "claude":
                cmd = [*argv, "-p", ask, "--max-turns", "1", "--output-format", "text"]
                if settings.get("claude_model") and SAFE_TOKEN.match(str(settings["claude_model"])):
                    cmd += ["--model", settings["claude_model"]]
                env = _child_env(settings.get("use_subscription", True))
            else:
                cmd = [*argv, "exec", "--skip-git-repo-check", "--sandbox", "read-only", ask]
                env = _child_env(False)
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                               env=env, stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
            text = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            if r.returncode == 0 and re.search(r"ready", text, re.I):
                return out(True, text.splitlines()[-1] if text else "")
            blob = f"{text}\n{err}"
            if SIGNED_OUT.search(blob):
                return out(False, error=blob.strip()[-600:], hint=f"Sign in: run `{'claude' if backend == 'claude' else 'codex login'}` once and finish the sign-in in your browser, then test again.")
            return out(False, error=blob.strip()[-600:] or f"exit code {r.returncode}", hint="See the message above; if it mentions your plan or limits, check your subscription.")
        if backend == "anthropic":
            if not settings.get("anthropic_key"):
                return out(False, error="No API key yet.", hint="Paste your Claude API key, then test again.")
            client = _anthropic_client(settings["anthropic_key"], timeout)
            r = _anthropic_call(client, model=settings.get("anthropic_model") or ANTHROPIC_MODELS[0][0], max_tokens=1000,
                                output_config={"effort": "low"}, messages=[{"role": "user", "content": ask}])
            text = "".join(b.text for b in r.content if b.type == "text").strip()
            return out(True, text or "(answered)")
        # local server or the OpenAI API: one chat completion
        base = (settings.get("openai_url") or "").rstrip("/")
        key = settings.get("openai_key") or ""
        model = settings.get("openai_model") or (openai_models(base, key) or [""])[0]
        if not model:
            return out(False, error=f"No model to talk to at {base}.",
                       hint="In LM Studio, download a model and switch the server on (Developer tab), then pick it here." if backend == "openai" else "Pick a model.")
        body = {"model": model, "messages": [{"role": "user", "content": ask}], "max_completion_tokens" if "api.openai.com" in base else "max_tokens": 400}
        r = _post(base + "/chat/completions", body, key, timeout)
        text = (r["choices"][0]["message"].get("content") or "").strip()
        return out(True, text or "(answered)")
    except subprocess.TimeoutExpired:
        return out(False, error=f"No answer within {int(timeout)} s.", hint="It may be waiting for a sign-in: open it once yourself and sign in, then test again.")
    except urllib.error.HTTPError as e:
        return out(False, error=_http_words(e, "OpenAI" if backend == "openai_api" else "The server"))
    except urllib.error.URLError as e:
        return out(False, error=f"Couldn't reach {settings.get('openai_url')}: {e.reason}",
                   hint="Is LM Studio open with its server switched on (Developer tab → Start server)?" if backend == "openai" else "Check the internet connection.")
    except Exception as e:  # noqa: BLE001
        if backend == "anthropic":
            return out(False, error=_anthropic_error(e))
        return out(False, error=repr(e))


def python_exe() -> str:
    return sys.executable


def probe_tool_server(server: dict, timeout: float = 60) -> list[str]:
    """Start the tool server the way Claude/Codex would and list its tools (MCP over stdio). Raises on failure."""
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "ucsim-probe", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    proc = _spawn([server["command"], *server["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                  env={**os.environ, **server["env"]}, text=True, encoding="utf-8")
    try:
        proc.stdin.write("".join(json.dumps(m) + "\n" for m in msgs))
        proc.stdin.flush()
        box: dict = {}

        def read():
            for line in proc.stdout:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("id") == 2:
                    box["tools"] = [t["name"] for t in d.get("result", {}).get("tools", [])]
                    return
        t = threading.Thread(target=read, daemon=True)
        t.start()
        t.join(timeout)
        if "tools" not in box:
            if t.is_alive():
                raise RuntimeError(f"the tool server didn't answer within {timeout:g} s")
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            raise RuntimeError("the tool server stopped without answering: " + (proc.stderr.read(4000) if proc.poll() is not None else "(still running)"))
        return box["tools"]
    finally:
        _kill_tree(proc)
