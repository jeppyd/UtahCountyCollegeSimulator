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
