# LLM features without an API key

*Revised 2026-10-05. This replaces the paid-API plan in `LLM_ROADMAP.md`. Feature IDs, designs and the engine work (Phase 0) are unchanged; only **how the model is reached** changes. Nothing here needs an API key or a separate bill.*

## Three ways to reach a model

| Route | How it works | Uses | Good for | Limits |
|---|---|---|---|---|
| **A. Chat drives the simulator (MCP)** | A small `ucsim` MCP server exposes simulator tools (search entities, count a cohort, validate/preview/apply a what-if, query, person dossier, event chains, compare worlds, run experiments). You talk to **Claude Code / Claude Desktop** (Pro) or **Codex CLI** (Plus); the sim does the work and the web app updates live. | Pro or Plus | The best accuracy; agent-style work | Lives in the chat window, not the web UI. Counts against your plan's 5-hour and weekly limits. |
| **B. In-app buttons via your CLI** | The server runs `claude -p` (Pro login) or `codex exec` (Plus login) on your PC with schema-constrained JSON. | Pro or Plus | What-if box, Ask, Interview inside the web app | A few seconds per call; same plan limits. **Personal use only:** it can't be shipped to other people on your login. |
| **C. Local model** | Ollama on your PC (`localhost:11434`, schema-constrained JSON, tool calls). | Your hardware | Anything high-volume, always-on, instant, or meant for other people | Weaker than Claude/GPT; needs a decent GPU. |

ChatGPT web (Plus developer mode) and claude.ai web connectors can also use the MCP server, but only through a public HTTPS tunnel (e.g. cloudflared). That's optional; Claude Code, Claude Desktop and Codex CLI connect locally.

## Catalogue by route

✓ = works on that subscription. **Local** = needs a local model unless you'd pay for an API. *No LLM* = done in plain code.

| ID | Feature | Claude Pro | ChatGPT Plus | Local needed? |
|---|---|---|---|---|
| **New** | **`ucsim` MCP server** (no LLM itself; everything in A uses it) | ✓ | ✓ | — |
| F1 | Provider adapter (`claude_cli` / `codex_cli` / `ollama`), replacing the paid gateway | ✓ | ✓ | optional backend |
| F2 | Entity index, @mentions, map picker | *No LLM* | | |
| F3 | Grounding gates (citations, number checks) | *No LLM* | | |
| F4 | Eval & replay harness | ✓ slow (spread the 340 cases over days) | ✓ slow | optional, for fast regression runs |
| F5 | Job queue | *No LLM* | | |
| F6 | "What the model saw" log + plan-limit warnings (no $) | ✓ | ✓ | — |
| **W1** | **What-If Composer** ("Helaman Halls burned down") | ✓ A + B | ✓ A + B | no (local is possible but well short of the 99% target) |
| W2 | Say-It Cohort Builder | ✓ | ✓ | no (local is fine too) |
| W3 | Scenario Director (multi-step, conditional) | ✓ A | ✓ A | no |
| W4 | Policy-to-Scenario import (paste a document) | ✓ A | ✓ A | no |
| W5 | Drop-In (add a described person or group) | ✓ | ✓ | no |
| W6 | Rewind (fork from a past day) | ✓ (as W1) | ✓ | no |
| **T1** | **Ask the World** | ✓ A + B | ✓ A + B | no |
| T2 | Sit-Down Interview | ✓ (light use) | ✓ (light use) | for unlimited chatting |
| T3 | Rashomon mode | ✓ | ✓ | no |
| T4 | Discovery tours | ✓ on demand | ✓ on demand | for an automatic background queue |
| N1 | Why? lens on every number | ✓ but seconds per click | ✓ same | **recommended** (instant clicks), or a plain-code template |
| N2 | Trust card | *No LLM* (make it a template) | | |
| N3 | Life story / diary | ✓ one at a time | ✓ | for diaries of many people |
| N4 | Two Lives | ✓ | ✓ | no |
| N5 | Provo Ledger newspaper | ✓ on request | ✓ on request | for an automatic edition every sim week |
| N6 | Legends of Place | ✓ | ✓ | no |
| N7 | Live commentary while time runs | ✗ | ✗ | **yes** |
| A1 | Pre-registered experiment agent | ✓ (Claude Code is the agent) | ✓ (Codex) | no |
| A2 | Devil's advocate | ✓ | ✓ | no |
| A3 | Goal-seeker (inverse what-if) | ✓ (long runs may hit the 5-hour cap) | ✓ | no |
| A4 | Prediction duel | ✓ | ✓ | no |
| A5 | Analysis notebooks | ✓ (writes them in the repo) | ✓ | no |
| A6 | Classroom / policy tournament (several users) | ✗ (plans are personal) | ✗ | **yes** |
| C1–C10 | Co-scientist (mechanism forge, validation doctor, calibration, evidence audit, ODD sync, probes, survey steward, VOI designer, benchmark harvester, scenario fuzzer) | ✓ directly in Claude Code: no app code, just project skills and commands | ✓ in Codex | no |
| X1 | Shadow focal panel (thousands of LLM decisions) | ✗ | ✗ | **yes** |
| X2 | Bias audit of the persona model | ✓ small (~200 prompts over a few sessions) | ✓ small | for a full audit; it must audit whichever model voices T2/T3 |

**Dropped with the API:** dollar budgets, prompt-caching and Batches tuning, and the Opus-escalation switch. Model choice is whatever your CLI is set to.

**Needs local only (unless you'd pay):** N7, A6, X1, plus the automatic or high-volume versions of N1, N3, N5, T2, T4 and X2. Anything shipped to other people (the Windows installer, a shared demo) must use a local model or each person's own Claude Code login.

## Recommended build order

1. **Phase 0, engine** (no LLM, unchanged): new primitives (close a place, displace residents, inject events, ripple), housing rules, the IR and its validator.
2. **MCP server + entity index + project instructions** (`CLAUDE.md` / `AGENTS.md` "what-if compiler" guide). This alone makes **W1, W2, W3, W4, T1, A1–A5 and C1–C10** usable from Claude Code, Claude Desktop or Codex.
3. **Provider adapter, CLI backends**: the What-if box, Ask, Interview and Two Lives inside the web app.
4. **Ollama backend** (only if you want them): instant Why?, live commentary, shadow panel, automatic newspaper and diaries, classroom mode.

## Setup on your end

1. **Claude:** install Claude Code and sign in with `/login` using your Pro account. Make sure `ANTHROPIC_API_KEY` is **not** set anywhere; if it is, Claude Code bills that key instead of your plan. Claude Desktop is optional, for chatting with the sim.
2. **ChatGPT:** install Codex CLI and choose "Sign in with ChatGPT" (`codex login`; add `--device-auth` on a machine without a browser).
3. **Local (only for the local-only features):** install Ollama, then pull **Gemma 4 12B** for an 8–12 GB GPU, or **Qwen 3.6 27B** / **Gemma 4 26B** for a 24 GB GPU.
4. Nothing to buy. Long agent sessions can hit Pro's 5-hour cap, which is shared with your claude.ai chats.

## Terms, briefly

- **Fine:** your own local app calling your own Claude Code or Codex for personal use. Both vendors document this use, and it draws from your plan's limits.
- **Not allowed:** routing other people's requests through your Pro credentials (Anthropic says so explicitly). Never copy or share Codex's `auth.json`.
- **Unverified:** Pro's exact usage numbers (Anthropic publishes none). ChatGPT Plus developer-mode availability: the official guide says Plus, but the help page couldn't be read.

Sources: code.claude.com/docs/en/headless, /cli-reference, /legal-and-compliance; support.claude.com articles 11175166, 8325606, 15036540; learn.chatgpt.com/docs/auth, /non-interactive-mode, /extend/mcp; developers.openai.com/api/docs/guides/developer-mode; docs.ollama.com (structured outputs, tool calling, Claude Code integration).
