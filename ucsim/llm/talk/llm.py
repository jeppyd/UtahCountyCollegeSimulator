"""One structured call to the backend chosen for a talk feature (Ask the world or Interviews).

The backends are the What-if compiler's (llm/backends.py: Claude Code or Codex on the owner's subscription, or a local
OpenAI-compatible server such as LM Studio); the connection settings are the compiler's (~/.ucsim/llm.json). Which
backend each talk feature uses lives in ~/.ucsim/talk.json: by default the local model for interviews when one is
loaded (fast, private) and Claude for Ask the world. Tests set FAKE to a function and never call a model.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from .. import backends
from ..compiler import HOME, load_settings

TALK_FILE = HOME / "talk.json"
FEATURES = ("ask", "interview", "narrate", "dialogue")
CHOICES = ("auto", "claude", "codex", "openai", "anthropic", "openai_api")
DEFAULTS = {"ask_backend": "auto", "interview_backend": "auto", "narrate_backend": "auto", "dialogue_backend": "auto",
            "auto_dialogue": False, "sensitive": False}
FAKE = None          # tests: FAKE(feature, stage, system, prompt, schema) -> dict
PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def load() -> dict:
    s = dict(DEFAULTS)
    try:
        if TALK_FILE.exists():
            s.update({k: v for k, v in json.loads(TALK_FILE.read_text(encoding="utf-8")).items() if k in DEFAULTS})
    except Exception:  # noqa: BLE001
        pass
    return s


def save(new: dict) -> dict:
    s = load()
    for k, v in (new or {}).items():
        if k in ("ask_backend", "interview_backend", "narrate_backend", "dialogue_backend") and v in CHOICES + ("off",):
            s[k] = v
        elif k in ("sensitive", "auto_dialogue"):
            s[k] = bool(v)
    HOME.mkdir(parents=True, exist_ok=True)
    TALK_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")
    return s


def _local_ready(cs: dict) -> bool:
    return bool(cs.get("openai_model")) or bool(backends.openai_models(cs["openai_url"]))


def resolve(feature: str, ts: dict | None = None, cs: dict | None = None) -> str:
    """The backend a feature will use now: its own choice, or 'auto' (local for interviews when a model is loaded,
    else the What-if compiler's backend)."""
    ts = ts or load()
    cs = cs or load_settings()
    choice = ts.get(f"{feature}_backend", "auto")
    if choice != "auto":
        return choice
    if feature in ("interview", "dialogue") and _local_ready(cs):
        return "openai"
    return cs["backend"] if cs["backend"] != "openai" or _local_ready(cs) else "claude"


def status() -> dict:
    ts, cs = load(), load_settings()
    from ..compiler import status as cstatus
    st = cstatus()
    return {"settings": ts, "using": {f: resolve(f, ts, cs) for f in FEATURES},
            "features": {"ask": "Ask the world", "interview": "Interviews", "narrate": "Tell a scene as a story",
                         "dialogue": "Wording of conversations and texts"},
            "available": {"claude": bool(st["claude"]), "codex": bool(st["codex"]), "openai": bool(st["openai_models"]) or _local_ready(cs),
                          "anthropic": bool(cs.get("anthropic_key")), "openai_api": bool(cs.get("openai_api_key"))},
            "local_model": cs.get("openai_model") or (st["openai_models"] or [None])[0],
            "recommended": {"ask": "claude", "interview": "openai", "narrate": "claude", "dialogue": "openai"}}


def _pack(feature: str, system: str) -> Path:
    d = HOME / f"talk_{feature}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "system.md").write_text(system, encoding="utf-8")
    (d / "AGENTS.md").write_text(system, encoding="utf-8")
    return d


def complete(feature: str, stage: str, system: str, prompt: str, schema: dict, on_step, cancel: threading.Event) -> tuple[dict | None, str | None, str]:
    """(answer object or None, error or None, backend used)."""
    if FAKE is not None:
        try:
            return FAKE(feature, stage, system, prompt, schema), None, "fake"
        except Exception as e:  # noqa: BLE001
            return None, f"{e!r}", "fake"
    cs = load_settings()
    which = resolve(feature)
    s = {**cs, "max_turns": 3, "timeout": min(int(cs.get("timeout", 600)), 300)}
    if which == "claude":
        res = backends.run_claude(prompt, schema, _pack(feature, system), s, on_step, cancel, None)
    elif which == "codex":
        res = backends.run_codex(prompt, schema, _pack(feature, system), s, on_step, cancel, None)
    elif which == "anthropic":      # a Claude API key
        res = backends.run_anthropic(system, prompt, schema, s, on_step, cancel, None)
    elif which == "openai_api":     # an OpenAI API key
        from ..compiler import api_settings
        res = backends.run_openai(system, prompt, schema, api_settings(s), on_step, cancel, None)
    else:
        res = _openai(system, prompt, schema, s, on_step, cancel)
    return res.get("plan"), res.get("error"), which


def _openai(system: str, prompt: str, schema: dict, s: dict, on_step, cancel) -> dict:
    base = (s.get("openai_url") or "http://localhost:1234/v1").rstrip("/")
    model = s.get("openai_model") or (backends.openai_models(base) or [""])[0]
    if not model:
        return {"plan": None, "error": f"No model is loaded at {base} (start LM Studio's server and load a model)."}
    if cancel.is_set():
        return {"plan": None, "error": "cancelled"}
    on_step("start", f"Asking {model} on this computer")
    try:
        r = backends._post(base + "/chat/completions",
                           {"model": model, "temperature": 0.3, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                            "response_format": {"type": "json_schema", "json_schema": {"name": "talk", "strict": True, "schema": schema}}},
                           s.get("openai_key") or "lm-studio", float(s.get("timeout", 300)))
        txt = r["choices"][0]["message"].get("content") or ""
    except Exception as e:  # noqa: BLE001
        return {"plan": None, "error": f"Local model error: {e!r}"}
    obj = backends._json_from_text(txt)
    return {"plan": obj, "error": None if obj is not None else "The local model didn't return JSON."}


def prompt_file(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


ANSWER_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["sentences"], "properties": {
    "sentences": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["text", "claims"],
                                              "properties": {"text": {"type": "string"}, "claims": {"type": "array", "items": {"type": "string"}}}}}}}
TOOLS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["calls"], "properties": {
    "calls": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["tool", "args_json"],
                                          "properties": {"tool": {"type": "string"}, "args_json": {"type": "string"}}}}}}
