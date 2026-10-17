"""Backends share one set of lookup tools: the MCP server answers over stdio, Codex gets it through -c overrides, and
a local server's models are listed (LM Studio's richer API, or any OpenAI-compatible one)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from ucsim.api import server
from ucsim.llm import backends, compiler


def test_tool_server_answers_like_claude_and_codex_will_start_it():
    spec = compiler.tool_server("t", "http://127.0.0.1:1")
    assert spec is not None
    assert set(backends.probe_tool_server(spec)) == set(backends.TOOL_NAMES)


def test_codex_gets_the_same_tools_for_this_run_only():
    args = backends.codex_tool_args({"command": "C:\\Program Files\\x\\app.exe", "args": ["--mcp-server"],
                                     "env": {"UCSIM_URL": "http://127.0.0.1:8765", "UCSIM_JOB": "j1"}})
    kv = dict(a.split("=", 1) for a in args[1::2])
    assert args[::2] == ["-c"] * len(kv)
    assert json.loads(kv["mcp_servers.ucsim.command"]) == "C:\\Program Files\\x\\app.exe"    # valid TOML string, escapes kept
    assert kv["mcp_servers.ucsim.default_tools_approval_mode"] == '"approve"' and kv["mcp_servers.ucsim.required"] == "false"
    assert kv["mcp_servers.ucsim.env"] == '{UCSIM_URL="http://127.0.0.1:8765",UCSIM_JOB="j1"}'
    assert backends.codex_tool_args(None) == []
    assert {t["function"]["name"] for t in backends.OPENAI_TOOLS} == set(backends.TOOL_NAMES)


@pytest.fixture
def fake_server():
    routes = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            routes.setdefault("_posts", []).append((self.path, body))
            handler = routes.get(("POST", self.path))
            self.send_response(200 if handler else 404)
            self.end_headers()
            if handler:
                self.wfile.write(json.dumps(handler(body)).encode())

        def do_GET(self):
            body = routes.get(self.path)
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            if body is not None:
                self.wfile.write(json.dumps(body).encode())

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield routes, f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def test_lm_studio_models_loaded_first_without_embeddings(fake_server):
    routes, url = fake_server
    routes["/api/v0/models"] = {"data": [{"id": "qwen-14b", "type": "llm", "state": "not-loaded"},
                                         {"id": "nomic-embed", "type": "embeddings", "state": "loaded"},
                                         {"id": "gemma-12b", "type": "llm", "state": "loaded"}]}
    assert [(m["id"], m["loaded"]) for m in backends.local_models(url)] == [("gemma-12b", True), ("qwen-14b", False)]
    del routes["/api/v0/models"]
    routes["/v1/models"] = {"data": [{"id": "llama3.1:8b"}, {"id": "nomic-embed-text"}]}        # Ollama-style
    assert backends.openai_models(url) == ["llama3.1:8b"]
    assert backends.local_models("http://127.0.0.1:9/v1") == []


def test_models_endpoint_is_local_only(fake_server):
    routes, url = fake_server
    routes["/v1/models"] = {"data": [{"id": "m1"}]}
    c = TestClient(server.app)
    assert c.get("/api/whatif/llm/models", params={"url": url}).json()["models"][0]["id"] == "m1"
    assert c.get("/api/whatif/llm/models", params={"url": url}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.get("/api/whatif/llm/models", params={"url": "file:///etc/passwd"}).status_code == 400


def test_lm_studio_v1_listing_and_loading(fake_server):
    routes, url = fake_server
    routes["/api/v1/models"] = {"models": [
        {"type": "llm", "key": "qwen-14b", "display_name": "Qwen 14B", "params_string": "14B", "size_bytes": 9.1e9,
         "max_context_length": 131072, "loaded_instances": []},
        {"type": "embedding", "key": "nomic-embed", "loaded_instances": [{"id": "nomic-embed", "config": {}}]},
        {"type": "llm", "key": "gemma-12b", "max_context_length": 32768,
         "loaded_instances": [{"id": "gemma-12b", "config": {"context_length": 4096}}]}]}
    models = backends.local_models(url)
    assert [(m["id"], m["loaded"], m["context"]) for m in models] == [("gemma-12b", True, 4096), ("qwen-14b", False, None)]
    assert models[1]["params"] == "14B" and models[1]["size_gb"] == 9.1
    routes[("POST", "/api/v1/models/unload")] = lambda b: {"instance_id": b["instance_id"]}
    routes[("POST", "/api/v1/models/load")] = lambda b: {"type": "llm", "instance_id": b["model"], "load_time_seconds": 3.2,
                                                         "status": "loaded", "load_config": {"context_length": b["context_length"]}}
    r = backends.load_local_model(url, "qwen-14b", 32768, unload_others=True)
    assert r["ok"] and r["context"] == 32768 and r["unloaded"] == ["gemma-12b"]          # the other chat model made room
    r = backends.load_local_model(url, "gemma-12b", 65536, unload_others=False)            # reload: capped at its maximum
    assert r["ok"] and r["context"] == 32768 and r["unloaded"] == ["gemma-12b"]
    assert not backends.load_local_model(url, "nope")["ok"]
    del routes[("POST", "/api/v1/models/load")]
    assert "0.4" in backends.load_local_model(url, "qwen-14b")["error"]                    # older LM Studio: explained


def test_codex_models_and_reasoning(monkeypatch, tmp_path):
    catalog = {"models": [
        {"slug": "b-model", "display_name": "B", "visibility": "list", "priority": 2, "default_reasoning_level": "medium",
         "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}, {"effort": "ultra"}]},
        {"slug": "a-model", "display_name": "A", "visibility": "list", "priority": 1, "default_reasoning_level": "low",
         "supported_reasoning_levels": [{"effort": "low"}, {"effort": "max"}]},
        {"slug": "hidden", "visibility": "hide", "priority": 0, "supported_reasoning_levels": []}]}
    monkeypatch.setattr(backends, "resolve_cli", lambda name, override=None: (["codex"], None))
    monkeypatch.setattr(backends, "_run_quick", lambda argv, timeout=20: type("R", (), {"stdout": json.dumps(catalog)})())
    backends._codex_models_cache.clear()
    ms = backends.codex_models()
    assert [m["slug"] for m in ms] == ["a-model", "b-model"]                 # Codex's order, hidden ones left out
    assert ms[1]["efforts"] == ["low", "high"]                               # "ultra" (sub-agents) isn't offered
    monkeypatch.setattr(compiler, "HOME", tmp_path)
    monkeypatch.setattr(compiler, "SETTINGS_FILE", tmp_path / "llm.json")
    assert compiler.save_settings({"codex_effort": "high"})["codex_effort"] == "high"
    assert compiler.save_settings({"codex_effort": "ultra; rm -rf"})["codex_effort"] == ""
