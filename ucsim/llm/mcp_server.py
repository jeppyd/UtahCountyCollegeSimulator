"""The simulator's tools for Claude Code (MCP over stdio): look things up, count people, check a draft plan.

Claude Code starts this process for one compile; each tool call is forwarded to the running simulator server
(UCSIM_URL), which answers from the live world. Read-only: nothing here can change the world.
"""
from __future__ import annotations

import json
import os
import urllib.request

from mcp.server.fastmcp import FastMCP

URL = os.environ.get("UCSIM_URL", "http://127.0.0.1:8000").rstrip("/")
JOB = os.environ.get("UCSIM_JOB", "")
mcp = FastMCP("ucsim")


def _call(name: str, args: dict) -> str:
    req = urllib.request.Request(f"{URL}/api/whatif/tool/{name}", data=json.dumps(args).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-UCSIM-Job": JOB})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode()
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": f"simulator unreachable: {e}"})


@mcp.tool()
def search_entities(query: str, kinds: list[str] | None = None, limit: int = 8) -> str:
    """Find people, housing complexes, venues, wards, employers, clubs/teams/institute classes, congregations, majors,
    neighborhoods, cities, schools, and model concepts (field, event, rule, preset) by name. Returns exact refs
    (e.g. complex:587), a description, how many people are linked now, and a ready-made `who` filter."""
    return _call("search_entities", {"query": query, "kinds": kinds, "limit": limit})


@mcp.tool()
def describe_entity(ref: str) -> str:
    """Details of one entity by ref, e.g. complex:587, ward:12, person:4031, venue_type:gym."""
    return _call("describe_entity", {"ref": ref})


@mcp.tool()
def count_people(who: dict) -> str:
    """Count how many people a `who` population filter selects right now (and normalize it). Use it to sanity-check
    a filter before putting it in the plan."""
    return _call("count_people", {"who": who})


@mcp.tool()
def validate_plan(plan: dict) -> str:
    """Check a draft plan exactly as the simulator will: returns ok, errors to fix, warnings to consider, and a
    plain-language summary of each change with how many people it reaches. Call it before your final answer."""
    return _call("validate_plan", {"plan": plan})


if __name__ == "__main__":
    mcp.run()
