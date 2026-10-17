# Setting up the What-if model: a guide for AI assistants

## For people: how to use this file

You don't need to understand anything below. Give this file to an AI assistant and let it walk you through.

- **An assistant that can run commands on your computer** (Claude Code, Codex, Cursor…): open it in the
  simulator's folder, or anywhere, and say:
  > Read docs/AI_SETUP_GUIDE.md from the Provo–Orem simulator and set up its What-if model for me.
- **A chat assistant** (claude.ai, ChatGPT): attach this file, or paste its link, and say:
  > Read this guide and walk me through setting up the simulator's What-if model, one step at a time.

It will ask which subscriptions you have and what computer you're on, then do or explain each step.

---

## For the assistant

Your job: connect the simulator's **Describe it** box (What-if tab) to a language model, and prove it works.
Follow this guide literally. It describes this exact app; don't substitute general knowledge where they differ.

### Ground rules

1. **No paid API keys.** Everything here runs on subscriptions the person already has (Claude Pro/Max, ChatGPT
   Plus) or on their own computer. Never ask for, create or store an Anthropic or OpenAI API key. If
   `ANTHROPIC_API_KEY` is set, Claude Code would bill that key instead of the subscription. Tell the person and
   offer to remove it from their environment. The simulator already strips it when it runs Claude Code.
2. **Ask before installing anything** and say what it is: "Claude Code, Anthropic's free command-line program".
3. **Never handle passwords.** Sign-ins happen in the person's browser.
4. **Change only what this guide names:** the simulator's settings file, or its settings API. Leave every other
   config file alone.
5. **Verify after every step** with the checks in [Verify](#verify), and tell the person plainly what worked.
6. If you can't run commands, give **one step at a time**, written for someone who has never used a terminal.
   Say how to open the terminal, what to paste, what they should see, and what to send back to you.

### How the simulator uses a model (facts)

- The person types a What-if. The simulator sends the model a guide and a catalog of every lever, plus the
  request. The model returns a structured plan, which the simulator checks before running anything. **The
  model never decides what simulated people do.**
- **Three backends**, chosen in the What-if tab under ⚙ or in the settings file:

  | `backend` | What it runs | Account | Notes |
  |---|---|---|---|
  | `claude` (recommended) | Claude Code headless (`claude -p`) | Claude Pro or Max (not the free plan) | Best plans, 10–30 s each |
  | `codex` | Codex CLI (`codex exec`) | ChatGPT Plus (or higher) | Close behind Claude |
  | `openai` | Any OpenAI-compatible local server: LM Studio (default) or Ollama | None | Quality depends on model size and GPU |

- **Lookup tools.** All three can use four read-only tools while they work: search the world, describe a thing,
  count people, check a draft plan. For Claude and Codex the simulator starts a small tool server (MCP over stdio) itself:
  - **from source:** `python -m ucsim.llm.mcp_server`, which needs the `mcp` package from `pip install -e .`;
  - **installed Windows app:** the app's own `.exe` started with `--mcp-server`.

  For local models the simulator runs the tools itself. Nothing for you to configure. The person can switch
  the tools off with the "let it look things up" checkbox, which is worth doing for small local models that
  call tools badly.
- **Settings file:** `~/.ucsim/llm.json`. On Windows that is `%USERPROFILE%\.ucsim\llm.json`; the `UCSIM_HOME`
  environment variable moves the folder. Keys (anything else is ignored):

  | Key | Values | Default |
  |---|---|---|
  | `backend` | `"claude"`, `"codex"`, `"openai"` | `"claude"` |
  | `claude_model` | `""` (Claude Code's default), `"sonnet"`, `"opus"`, `"haiku"` | `""` |
  | `claude_effort` | `""`, `"low"`, `"medium"`, `"high"` | `""` |
  | `codex_model` | `""` or a Codex model name | `""` |
  | `codex_effort` | `""` (the model's default), `"minimal"`, `"low"`, `"medium"`, `"high"`, `"xhigh"`, `"max"` (what each model supports: `codex debug models`) | `""` |
  | `openai_url` | local server base URL **ending in `/v1`** | `"http://localhost:1234/v1"` |
  | `openai_model` | `""` (first loaded model) or a model id exactly as the server lists it | `""` |
  | `use_tools` | `true` / `false` | `true` |
  | `max_turns` | 5–80 | 40 |
  | `timeout` | seconds per plan, 60–1800 | 600 |
  | `claude_path`, `codex_path` | full path to the program, **only** if it isn't found on PATH (file only) | absent |

  `UCSIM_LLM_BACKEND=claude|codex|openai` in the environment overrides `backend`.
- **The running app's address.**
  - **Installed Windows app:** usually `http://127.0.0.1:8765`. If that port was busy it picks another; the
    address is in the last `serving http://…` line of `%LOCALAPPDATA%\ProvoOremSimulator\simulator.log`.
  - **From source** (`python -m ucsim.api.server`): `http://127.0.0.1:8000`, or the port given with `--port`.
- **Settings API** (only while the app is running; preferred over editing the file because it validates values):
  - `GET  {app}/api/whatif/llm/status?refresh=1`: what the app sees right now (see [Verify](#verify)).
  - `POST {app}/api/whatif/llm/settings` with a JSON body of the keys to change; it returns the saved settings.
  - `GET  {app}/api/whatif/llm/models?url=<openai_url>`: the models a local server offers.
  - `POST {app}/api/whatif/llm/load` with `{"model": "<id>", "context_length": 32768}`: has LM Studio (0.4+) load that model with that context window, unloading other models first (`"unload_others": false` to keep them). It blocks until the model is loaded.

  These answer only requests from the same computer. Plain `curl` or PowerShell works; a web page on another
  site won't.

  ```bash
  curl -s "http://127.0.0.1:8765/api/whatif/llm/status?refresh=1"
  curl -s -X POST http://127.0.0.1:8765/api/whatif/llm/settings -H "Content-Type: application/json" -d '{"backend":"openai"}'
  ```
  ```powershell
  Invoke-RestMethod "http://127.0.0.1:8765/api/whatif/llm/status?refresh=1"
  Invoke-RestMethod -Method Post http://127.0.0.1:8765/api/whatif/llm/settings -ContentType "application/json" -Body '{"backend":"openai"}'
  ```

### Step 1: choose the backend

Ask the person:
1. Do you pay for **Claude Pro or Max**? Then use `claude`. Stop asking.
2. Otherwise, do you pay for **ChatGPT Plus**? Then use `codex`.
3. Otherwise, or if they want it free and offline, use `openai` with LM Studio. Check their graphics card first
   (see [Choosing a local model](#choosing-a-local-model)); with less than about 8 GB of video memory, or 16 GB of
   unified memory on a Mac, warn them that plans will often fail the checks.

Also ask: Windows or Mac? The installed app, or running from source?

### Step 2A: Claude (`backend: "claude"`)

1. Is it installed? Run `claude --version`. A version number means yes; skip to step 3.
2. Install it (ask first):
   - Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`
   - macOS / Linux: `curl -fsSL https://claude.ai/install.sh | bash`

   Then open a **new** terminal window and check `claude --version` again. If it still isn't found, the install
   folder (Windows: `%USERPROFILE%\.local\bin`) isn't on PATH yet; a new window or a sign-out/in fixes it. The
   simulator also looks in that folder itself.
3. Sign in: the person runs `claude` in a terminal, signs in with their Claude account in the browser, then types
   `/exit`. You can't do this for them.
4. Check `ANTHROPIC_API_KEY` isn't set:
   - Windows: `echo $env:ANTHROPIC_API_KEY`
   - Mac/Linux: `echo $ANTHROPIC_API_KEY`

   If it prints something, offer to remove it from their environment settings.
5. Set `backend` to `"claude"`, through the settings API or the ⚙ panel (Claude is the default anyway).
6. [Verify](#verify). The status should show `"claude": "<version>"` and `"ready": true`.

### Step 2B: Codex (`backend: "codex"`)

1. Is it installed? Run `codex --version`.
2. If not:
   - It needs Node.js: check `node --version`; if missing, install the LTS release from nodejs.org.
   - Then, in a new terminal: `npm install -g @openai/codex`.
3. Sign in: the person runs `codex login` and chooses **Sign in with ChatGPT**. On a machine without a browser,
   use `codex login --device-auth`.
4. Set `backend` to `"codex"`.
5. [Verify](#verify). The status should show `"codex": "<version>"` and `"ready": true`. If `codex_note` is set,
   the simulator found a launcher it can't run safely: reinstall Codex, or set `codex_path` in the settings file
   to the full path of the real `codex` program.

The simulator passes the lookup tools to Codex for each run with `-c mcp_servers.ucsim.*` overrides. Nothing is
written to the person's `~/.codex/config.toml`.

### Step 2C: LM Studio (`backend: "openai"`)

1. Install LM Studio from lmstudio.ai and open it once. Opening it also installs its `lms` command; check with
   `lms --help` in a new terminal.
2. Download a model (see [Choosing a local model](#choosing-a-local-model)), either:
   - in the app: **Discover** tab → search → Download;
   - or from the terminal: `lms get <model-name>`.

   Then `lms ls` lists what's on disk.
3. **Load it with a big enough context window.** Easiest: in the simulator's ⚙ panel, pick the model and press **Load** (or call `POST {app}/api/whatif/llm/load`); it uses 32k. By hand: The simulator's instructions are about 12,500 tokens, and LM
   Studio often loads models with only 4,096. Load with **16,384 or more; 32,768 is comfortable**:
   - terminal: `lms load <model-name> --context-length 32768` (add `--gpu max` to use the graphics card fully);
   - app: **Developer** tab → load the model → open its settings → **Context Length**.

   `lms ps` shows what's loaded.
4. Start the server, either with `lms server start` or with the **Developer** tab → **Start server** switch. It
   listens on `http://localhost:1234`. Check it: `curl -s http://localhost:1234/v1/models`.
5. Settings:
   - `backend: "openai"`;
   - `openai_url: "http://localhost:1234/v1"` (the default);
   - `openai_model`: the id exactly as listed by `{app}/api/whatif/llm/models` or `/v1/models`. An empty value
     means the first loaded model.

   In the ⚙ panel the person can just pick from the **Model** dropdown, which fills itself from LM Studio.
6. [Verify](#verify). The status should list the model in `openai_models` and show `"ready": true`. The ⚙ panel
   warns in orange if the loaded model's context window is too small.

### Step 2D: Ollama (`backend: "openai"`)

1. Install Ollama (ollama.com) and pull a model, e.g. `ollama pull <model>`.
2. Its default context window is small too. Before starting Ollama, set the environment variable
   `OLLAMA_CONTEXT_LENGTH=32768`, then restart Ollama.
3. Settings: `backend: "openai"`, `openai_url: "http://localhost:11434/v1"`, `openai_model: "<model>"` (with its
   tag, e.g. `name:14b`, exactly as `ollama list` shows it).
4. [Verify](#verify).

### Choosing a local model

- Check memory:
  - Windows / Linux with NVIDIA: `nvidia-smi` (look at total memory).
  - Windows generally: `Get-CimInstance Win32_VideoController | Select Name` (this reports memory unreliably,
    so look the card up).
  - Mac: `sysctl -n hw.memsize` gives unified memory in bytes; about 65% of it is usable by models.
- Rough fit for 4-bit ("Q4") downloads with a 32k context:

  | Video memory | Model size |
  |---|---|
  | 8 GB | 7–9B parameters |
  | 12 GB | 12–14B |
  | 16 GB | 14–20B |
  | 24 GB+ | 27–32B |
- Prefer current **instruct** models that list **tool use** in LM Studio's Discover tab and are known to be good
  at structured JSON: recent Qwen and Gemma instruct models, or OpenAI's open-weight gpt-oss-20b on 16 GB. Under
  about 8B, plans often fail the simulator's checks. Suggest turning **off** "let it look things up" if a small
  model loops on tool calls.

### Verify

1. **Status:** `GET {app}/api/whatif/llm/status?refresh=1`. Read these fields:

   | Field | Meaning |
   |---|---|
   | `settings.backend` | the backend in use |
   | `ready` | `true` when that backend was found and answers |
   | `claude` / `codex` | the installed version, or `null` if not found |
   | `claude_note` / `codex_note` | why a found program can't be used, with the fix |
   | `openai_models` | models the local server lists (for `backend: "openai"`) |
   | `mcp` | whether the lookup tools are available (from source this needs `pip install -e .`) |
   | `api_key_in_env` | `true` means `ANTHROPIC_API_KEY` is set; see ground rule 1 |
   | `desktop` | `true` for the installed app |
2. **A real test.**
   - Have the person open the **What-if** tab. The pill at the top of the Describe box should read
     **● Claude Code**, **● Codex** or **● Local model**, not "set up".
   - Have them type `What if a snowstorm closes campus for two days?` and press Enter.
   - Steps should appear within seconds. Within about a minute (several minutes on a slow local model), a plan
     card with changes should appear. With tools on, the steps include lines like "Counting people" and
     "Draft checks out".
3. Tell the person it's done and what they're using.

### Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Status `claude: null` although `claude --version` works in your terminal | The app was started before the install: quit and reopen the app. If it still fails, set `claude_path` in the settings file. |
| "ended without an answer… is Claude Code signed in?" | Run `claude` once and sign in. |
| "You've hit your usage limit" | The plan's 5-hour or weekly limit. Wait, or switch backend. |
| `codex_note` / `claude_note` mentions an npm launcher | Set `codex_path` / `claude_path` to the real program, or (Claude) reinstall with the native installer. |
| Local: "No model is loaded at …" | Start LM Studio's server and load a model, or set `openai_model`. |
| Local: errors about context, or a plan that's cut off or is nonsense | The context window is too small. Reload the model with `--context-length 32768`; for Ollama, set `OLLAMA_CONTEXT_LENGTH`. |
| Local: plan rows marked ✕, or repeated "asking for a fix" | The model is too small or bad at JSON. Try a larger model, or turn off "let it look things up". |
| Local: status lists no models but LM Studio is running | Wrong address. It must end in `/v1`, and LM Studio's server switch must be on. |
| "only accepted from this computer" (403) | You called the settings API from a web page or another machine. Call it locally with curl or PowerShell. |
| From source: a tip says `pip install mcp` | Run `pip install -e .` in the simulator folder (it adds `mcp`), then restart the app. |

Human-facing documentation of the feature: `docs/WHATIF_LLM.md`.
