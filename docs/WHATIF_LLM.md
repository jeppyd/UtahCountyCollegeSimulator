# Describe a What-if in plain language

The **Describe it** tab in the What-if builder lets you type any scenario: "the Church announces that alcohol is now permitted", "Helaman Halls burns down", "a snowstorm shuts Provo down for a week". A language model turns it into a concrete plan of changes to the simulated world. You review the plan, untick anything you don't want, and run it. The simulation, not the model, decides how every person responds.

It runs on the subscriptions you already have: **no API key and no extra bill.**

## Setup (one time)

> **Not technical?** Give [AI_SETUP_GUIDE.md](AI_SETUP_GUIDE.md) to an AI assistant (Claude, ChatGPT, Claude Code, Codex) and ask it to set this up for you. It's written for the assistant, step by step.

**Do you need to install anything?** For Claude or ChatGPT, yes, once: a small free program from Anthropic (*Claude Code*) or OpenAI (*Codex*) that you sign in to with your account. The simulator borrows that sign-in, which is how it uses your subscription with no API key. You never have to open it again afterwards; it runs out of sight when you press Send. For a local model you only need LM Studio or Ollama running; there's no account. The same steps, with copy buttons and a **Check again** button, are in the What-if tab under ⚙.

**Claude (recommended): uses your Claude Pro or Max plan** (the free plan doesn't include Claude Code)

1. Open PowerShell (Start → type *PowerShell* → Enter). On a Mac, open Terminal.
2. Install Claude Code:
   - Windows: `irm https://claude.ai/install.ps1 | iex`
   - Mac/Linux: `curl -fsSL https://claude.ai/install.sh | bash`
3. Open a new PowerShell window, type `claude` and press Enter. Sign in with your Claude account in the browser window that opens, then type `/exit`.
4. In the simulator's What-if tab, press ⚙ → **Check again**. It shows **✓ Claude Code is installed**.

Make sure `ANTHROPIC_API_KEY` isn't set on your computer; if it is, Claude Code would bill that key. (The simulator removes it from the environment it passes to Claude Code anyway.) If you run the simulator from source, `pip install -e .` adds `mcp`, which lets Claude look things up in the live world while it works; the installed app works without it.

In settings you can pick the model:
- **Default/Sonnet** is fast (10–30 s per plan) and works very well.
- **Opus** reasons more deeply for complicated scenarios and uses more of your limit.
- **Haiku** is quickest.

**ChatGPT: uses your ChatGPT Plus plan**

1. Install Node.js (the LTS download from nodejs.org).
2. In a new PowerShell window: `npm install -g @openai/codex`
3. `codex login` → *Sign in with ChatGPT*.
4. Pick *ChatGPT (Plus)* in the tab's settings and press **Check again**. Choose the **model** and **reasoning** level from the dropdowns (they list what your Codex offers); more reasoning is more careful but slower and uses more of your plan.

Codex gets the same lookup tools as Claude, for each run only; nothing is added to your Codex settings.

**Local model (LM Studio, Ollama): no account at all**

1. Install LM Studio (lmstudio.ai).
2. In its Discover tab, download a model: about 12–14B parameters for an 8–12 GB graphics card, 27–32B for 24 GB. Models under 8B often produce plans that fail the checks.
3. In the Developer tab, load the model with **Context Length** set to 16,384 or more (32,768 is comfortable; the simulator's instructions alone are about 12,500 tokens, and LM Studio often defaults to 4,096), and switch on **Start server** (`http://localhost:1234`).
4. Pick *Local model* in the tab's settings and keep the address. The **Model** dropdown lists every model LM Studio has downloaded. Pick one and press **Load**: the simulator loads it into LM Studio with a 32k context window (unloading other models first, unless you untick that) and saves it as your model. This needs LM Studio 0.4 or newer; with an older one, load the model in LM Studio's Developer tab. The panel warns, with a one-click fix, if a loaded model's context window is too small.

Ollama works too, at `http://localhost:11434/v1`; set `OLLAMA_CONTEXT_LENGTH=32768` before starting it.

**Settings** are stored in `~/.ucsim/llm.json`. You can also set `UCSIM_LLM_BACKEND=claude|codex|openai`.

## Using it

- **Type the idea** and press Enter. Shift+Enter starts a new line.
- **Tag exact things with `@`.** Type `@Hela…` and pick *Helaman Halls* from the list. People, housing complexes, venues, wards, employers, clubs, teams, institute classes, congregations, majors, neighborhoods, cities, schools, and even model concepts (a field, an event type, a rule, a ready-made What-if) can all be tagged. The model receives the exact id and a ready-made "who" filter, so "Helaman Halls" can't be confused with "BYU Creamery Outlet at Helamen". Every person and place page also has a **What if…** button that tags it for you.
- **Watch it think.** Each step appears live: reading the catalog, looking up a name, counting who would be affected, checking a draft.
- **Review the plan.** Each change shows:
  - what it does, in plain words;
  - who it applies to, and how many people that is right now;
  - when it starts and how long it lasts;
  - why it's there.

  Untick any change you don't want. The plan also lists:
  - what the model **couldn't** model and how it approximated it;
  - its assumptions;
  - its **predictions**.
- **Refine it** by replying: "make it stronger", "only freshmen", "also close the Creamery". The model revises the whole plan.
- **Run it.** *Split the world* starts a new What-if; *Add to What-if* adds the plan to the running one. Choose how long to run first.
- **See how it plays out.** The What-if overview shows your request and each change's reach. It also tracks the model's predictions against the simulation as time runs: *✓ as predicted*, *✕ the opposite* or *… too early*. For a new spreading practice (say, beards at BYU), it shows the adoption curve.

## How it works

```
your words + tagged entities + the conversation
        │
        ▼
 Claude Code (headless, your login)  ◄── guide + full lever catalog (appended system prompt)
        │  tools over MCP: search_entities · describe_entity · count_people · validate_plan
        ▼
 structured plan (JSON schema)  ──►  server validator  ──(errors? one repair round)──►  receipt
                                                                                          │ you approve
                                                                                          ▼
                                                        intervention atoms  ──►  the What-if world forks
```

- **The catalog** (`ucsim/llm/levers.py`) is generated from the registries. It contains every lever that exists, with exact ids, bounds, timing and pitfalls:
  - world switches and norms;
  - persistent nudges on feelings and behaviors;
  - injectable events and custom shocks;
  - person traits that can safely change;
  - every mechanism parameter with its evidence level;
  - closures, place changes, spreading practices, new venues;
  - the population-filter language.
- **The guide** (`ucsim/llm/prompts/guide.md`) teaches the model how to think: trace consequences through the model's domains, prefer structural levers, model reactions to the news per group, size effects honestly, time them, and be candid about what's missing.
- **The validator** (`ucsim/llm/plan.py`) is the gatekeeper. Only known levers, valid ids and exact category labels pass, and values are clipped to safe bounds. It fixes what it safely can (for example the case of labels) and rejects what it can't, with a reason.
- **Engine primitives** (`ucsim/engine/interventions.py`):
  - **`world`**: policy switches, norms, prices and weather.
  - **`param`**: mechanism parameters.
  - **`agent`**: a lasting change to a trait.
  - **`offset`**: a persistent nudge on a feeling or behavior for a group, re-checked weekly. It appears as the "What-if nudge" term in every decomposition.
  - **`event`** and **`shock`**: real or custom events that are appraised, felt and remembered like any other, and that can trigger coping. They appear in event chains with their own labels.
  - **`close`**: a complex (residents are rehoused under the housing rules) or venues.
  - **`place`**: a complex's rent, beds, quality or contracted status.
  - **`practice`**: a new behavior that spreads by complex contagion through friendships.
  - **`venue`**: a new business opens.

  Every random choice uses its own stream or a stable hash, so the Original world is never disturbed and do-nothing changes leave the twin identical.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Claude Code isn't installed or isn't on PATH" | Install it; on Windows, open a new terminal after installing so PATH updates. |
| Claude Code or Codex is installed somewhere PATH doesn't reach | Add `"claude_path": "C:\\path\\to\\claude.exe"` (or `"codex_path"`) to `~/.ucsim/llm.json`. |
| "only accepted from this computer" | The What-if endpoints answer only pages opened from this machine (localhost), so other websites can't use your plan. |
| "ended without an answer… is Claude Code signed in?" | Run `claude` once in a terminal and sign in. |
| A note says to `pip install mcp` | Run `pip install -e .` or `pip install mcp`. Claude works without it but can't check its plan while it works. |
| You hit a usage limit | Claude Pro has rolling 5-hour and weekly limits shared with claude.ai. Wait for the window to reset, or switch to Codex or a local model in settings. |
| A plan has red ✕ rows | Those changes were rejected by the validator (the reason is shown) and won't run. Reply asking for a fix, or run the rest. |

What it can't do: change the engine's code. If your idea needs a mechanism the model doesn't have (grooming, curfews, a specific building with no entity), the plan says so and uses the closest honest approximation.
