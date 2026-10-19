// Connect an AI: a guided setup for people who have never used a terminal. Three steps — choose (Claude, ChatGPT or a
// model on this computer; a subscription or an API key), connect (what to install or paste, checked live) and test
// (a one-word round trip that proves the sign-in or key works). Opened from the top bar, the settings menu and the
// What-if panel; settings are saved on this computer (ucsim/llm/compiler.py).
import { useEffect, useState, type ReactNode } from 'react'
import { create } from 'zustand'
import { api, STATIC } from '../api'
import { G, useAsync } from '../game'
import './aisetup.css'

type Backend = 'claude' | 'codex' | 'openai' | 'anthropic' | 'openai_api'
export const BACKEND_NAME: Record<string, string> = {
  claude: 'Claude (subscription)', codex: 'ChatGPT (subscription)', openai: 'Local model',
  anthropic: 'Claude (API key)', openai_api: 'ChatGPT (API key)',
}

export const useAiSetup = create<{ open: boolean; ver: number; show: () => void; hide: () => void; bump: () => void }>(set => ({
  open: false, ver: 0,
  show: () => set({ open: true }), hide: () => set({ open: false }), bump: () => set(s => ({ ver: s.ver + 1 })),
}))

/** The AI connection's status (shared by the top bar pill, the What-if panel and the setup). */
export function useAiStatus() {
  const ver = useAiSetup(s => s.ver)
  return useAsync(() => (STATIC ? Promise.resolve(null) : api.llmStatus(ver > 0)), [ver], { key: 'llm-status' })
}

/** A small pill: which AI is connected, or "Connect an AI". Click to open the setup. */
export function AiPill() {
  const st = useAiStatus()
  const show = useAiSetup(s => s.show)
  const s: any = st.data
  if (STATIC || !s) return null
  return (
    <button className={`pill ai-pill ${s.ready ? 'ok' : 'warn'}`} onClick={show} title="The AI that turns your words into What-ifs">
      <i className="dot" />{s.ready ? BACKEND_NAME[s.settings?.backend] ?? 'AI' : 'Connect an AI'}
    </button>
  )
}

function Cmd({ c }: { c: string }) {
  const [done, setDone] = useState(false)
  return (
    <span className="ai-cmd"><code>{c}</code>
      <button className="btn ghost small" onClick={() => navigator.clipboard?.writeText(c).then(() => { setDone(true); window.setTimeout(() => setDone(false), 1500) })}>{done ? 'Copied' : 'Copy'}</button>
    </span>
  )
}
function Found({ ok, children }: { ok: boolean; children: ReactNode }) {
  return <p className={`ai-found ${ok ? 'ok' : 'warn'}`}>{ok ? '✓' : '○'} {children}</p>
}

// ---------------------------------------------------------------- step 1: choose
const CHOICES: { provider: string; blurb: string; options: { b: Backend; title: string; cost: string; effort: string; rec?: boolean }[] }[] = [
  { provider: 'Claude', blurb: 'by Anthropic',
    options: [
      { b: 'claude', title: 'I have a Claude Pro or Max plan', cost: 'Included in your plan (counts toward its usage limits).', effort: 'A one-time install of the free Claude Code app (about 5 minutes, one pasted command).', rec: true },
      { b: 'anthropic', title: 'Use an API key instead', cost: 'Pay as you go: a few cents per What-if, billed by Anthropic.', effort: 'Nothing to install: paste a key from console.anthropic.com.' },
    ] },
  { provider: 'ChatGPT', blurb: 'by OpenAI',
    options: [
      { b: 'codex', title: 'I have a ChatGPT Plus or Pro plan', cost: 'Included in your plan (counts toward its usage limits).', effort: 'A one-time install of Node.js and the free Codex app (about 10 minutes).' },
      { b: 'openai_api', title: 'Use an API key instead', cost: 'Pay as you go: a few cents per What-if, billed by OpenAI.', effort: 'Nothing to install: paste a key from platform.openai.com.' },
    ] },
  { provider: 'On this computer', blurb: 'LM Studio or Ollama',
    options: [
      { b: 'openai', title: 'Run a free model on my computer', cost: 'Free and private: nothing leaves your computer.', effort: 'Install LM Studio and download a model (several GB). Slower and less careful unless you have a strong graphics card.' },
    ] },
]

function Choose({ current, pick }: { current?: string; pick: (b: Backend) => void }) {
  return (
    <div className="ai-choose">
      <p className="ai-lede">The simulator can turn a plain-English idea ("what if rent went up 20%?") into exact changes to the world. For that it
        needs an AI model. Pick the one you already use; you can change it any time.</p>
      {CHOICES.map(g => (
        <div key={g.provider} className="ai-group">
          <div className="ai-group-h"><b>{g.provider}</b><span>{g.blurb}</span></div>
          <div className="ai-options">
            {g.options.map(o => (
              <button key={o.b} className={`ai-option ${current === o.b ? 'on' : ''}`} onClick={() => pick(o.b)}>
                <b>{o.title}{o.rec && <span className="ai-rec">recommended</span>}</b>
                <span>{o.cost}</span>
                <small>{o.effort}</small>
              </button>
            ))}
          </div>
        </div>
      ))}
      <p className="ai-note">Not sure? If you pay for Claude or ChatGPT already, use your plan. If you'd rather not install anything, an API key is
        the quickest. Either way, the simulator only sends your idea and a description of the simulation's settings, never anything else on your computer.</p>
    </div>
  )
}

// ---------------------------------------------------------------- step 2: connect
function Connect({ b, s, refresh, checking }: { b: Backend; s: any; refresh: () => void; checking: boolean }) {
  const win = s?.windows ?? /Win/.test(navigator.platform)
  const shell = win ? <>Open <b>PowerShell</b>: press the Start button, type <i>PowerShell</i>, press Enter.</> : <>Open the <b>Terminal</b> app (on a Mac: press ⌘ Space, type <i>Terminal</i>, press Enter).</>
  // while an app is being installed, look for it every few seconds
  const waiting = (b === 'claude' && !s?.claude) || (b === 'codex' && !s?.codex)
  useEffect(() => {
    if (!waiting) return
    const t = window.setInterval(refresh, 5000)
    return () => window.clearInterval(t)
  }, [waiting])
  const again = <button className="btn small" disabled={checking} onClick={refresh}>{checking ? 'Looking…' : 'Look again'}</button>

  if (b === 'claude') return (
    <div className="ai-connect">
      <Found ok={!!s?.claude}>{s?.claude ? <>Claude Code is installed ({s.claude}).</> : <>Claude Code isn't installed yet. This page notices by itself once it is.</>}</Found>
      {s?.claude_note && <p className="ai-warn">{s.claude_note}</p>}
      <ol className="ai-steps">
        <li>{shell}</li>
        <li>Paste this line and press Enter. It downloads and installs Claude Code (from claude.ai):<br />
          <Cmd c={win ? 'irm https://claude.ai/install.ps1 | iex' : 'curl -fsSL https://claude.ai/install.sh | bash'} /></li>
        <li>When it finishes, close that window, open a new one the same way, type <Cmd c="claude" /> and press Enter.
          A browser page opens: sign in with your Claude account (Pro or Max; the free plan doesn't include Claude Code).</li>
        <li>Back in the window, type <code>/exit</code> and press Enter. You never need to open it again; the simulator uses it out of sight.</li>
        <li>Press <b>Next</b> below to test it. {again}</li>
      </ol>
      {s?.api_key_in_env && <p className="ai-warn">An ANTHROPIC_API_KEY is set on this computer. The simulator hides it from Claude Code, so your plan is used, not API billing.</p>}
      <ModelRow label="Model">
        <select value={s?.settings?.claude_model ?? ''} onChange={e => save({ claude_model: e.target.value }, refresh)}>
          <option value="">Claude Code's default</option><option value="sonnet">Sonnet (fast, recommended)</option><option value="opus">Opus (most careful, uses more of your limit)</option><option value="haiku">Haiku (quickest)</option>
        </select>
      </ModelRow>
    </div>
  )

  if (b === 'codex') return (
    <div className="ai-connect">
      <Found ok={!!s?.codex}>{s?.codex ? <>Codex is installed ({s.codex}).</> : <>Codex isn't installed yet. This page notices by itself once it is.</>}</Found>
      {s?.codex_note && <p className="ai-warn">{s.codex_note}</p>}
      <ol className="ai-steps">
        <li>Install <b>Node.js</b>: download the "LTS" version from <a href="https://nodejs.org" target="_blank" rel="noreferrer">nodejs.org</a> and run it, accepting the defaults.</li>
        <li>{shell} (If it was already open, close it and open a new one so it finds Node.js.)</li>
        <li>Paste this and press Enter: <Cmd c="npm install -g @openai/codex" /></li>
        <li>Then this, and choose <b>Sign in with ChatGPT</b> in the browser page that opens: <Cmd c="codex login" /></li>
        <li>Press <b>Next</b> below to test it. {again}</li>
      </ol>
      {(s?.codex_models ?? []).length > 0 && <ModelRow label="Model">
        <select value={s?.settings?.codex_model ?? ''} onChange={e => save({ codex_model: e.target.value }, refresh)}>
          <option value="">Codex's default</option>
          {s.codex_models.map((m: any) => <option key={m.slug} value={m.slug}>{m.name}</option>)}
        </select>
      </ModelRow>}
    </div>
  )

  if (b === 'anthropic' || b === 'openai_api') return <KeyForm b={b} s={s} refresh={refresh} />
  return <LocalForm s={s} refresh={refresh} />
}

async function save(patch: any, then?: () => void) {
  await api.llmSettings(patch)
  then?.()
}

function ModelRow({ label, children }: { label: string; children: ReactNode }) {
  return <div className="ai-row"><span>{label}</span>{children}</div>
}

function KeyForm({ b, s, refresh }: { b: 'anthropic' | 'openai_api'; s: any; refresh: () => void }) {
  const claude = b === 'anthropic'
  const has = claude ? s?.settings?.has_anthropic_key : s?.settings?.has_openai_api_key
  const [key, setKey] = useState('')
  const [msg, setMsg] = useState('')
  const store = async () => {
    const k = key.trim()
    if (k.length < 20) { setMsg('That looks too short for an API key; copy the whole key.'); return }
    await api.llmSettings(claude ? { anthropic_key: k } : { openai_api_key: k })
    setKey(''); setMsg('Saved on this computer.'); refresh()
  }
  return (
    <div className="ai-connect">
      <Found ok={!!has}>{has ? <>A key is saved on this computer.</> : <>No key saved yet.</>}</Found>
      <ol className="ai-steps">
        {claude ? <>
          <li>Go to <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">console.anthropic.com</a> and sign in (or create an account; it's separate from a Claude.ai chat subscription).</li>
          <li>Under <b>Billing</b>, add a little credit (five dollars lasts a long time here).</li>
          <li>Under <b>API keys</b>, press <b>Create key</b>, name it "Provo–Orem simulator" and copy it. It starts with <code>sk-ant-</code>.</li>
        </> : <>
          <li>Go to <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">platform.openai.com</a> and sign in (an API account is separate from a ChatGPT subscription).</li>
          <li>Under <b>Billing</b>, add a little credit.</li>
          <li>Under <b>API keys</b>, press <b>Create new secret key</b> and copy it. It starts with <code>sk-</code>.</li>
        </>}
        <li>Paste it here and press <b>Save key</b>:
          <div className="ai-row"><input type="password" autoComplete="off" spellCheck={false} placeholder={has ? 'paste a new key to replace the saved one' : 'paste your key'} value={key} onChange={e => setKey(e.target.value)} style={{ flex: 1 }} />
            <button className="btn primary small" disabled={!key.trim()} onClick={store}>Save key</button></div>
          {msg && <span className="ai-note">{msg}</span>}
        </li>
      </ol>
      <ModelRow label="Model">
        {claude
          ? <select value={s?.settings?.anthropic_model ?? 'claude-opus-5-5'} onChange={e => save({ anthropic_model: e.target.value }, refresh)}>
              {(s?.anthropic_models ?? []).map((m: any) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          : (s?.openai_api_models ?? []).length
            ? <select value={s?.settings?.openai_api_model ?? ''} onChange={e => save({ openai_api_model: e.target.value }, refresh)}>
                <option value="">Pick a model…</option>
                {s.openai_api_models.map((m: string) => <option key={m} value={m}>{m}</option>)}
              </select>
            : <input type="text" placeholder={has ? 'a model name, e.g. from your OpenAI dashboard' : 'save your key first; the list appears here'} defaultValue={s?.settings?.openai_api_model ?? ''}
                onBlur={e => save({ openai_api_model: e.target.value.trim() }, refresh)} />}
      </ModelRow>
      <p className="ai-note">The key is stored only on this computer (in your home folder's .ucsim settings) and is sent only to {claude ? 'Anthropic' : 'OpenAI'}.
        {has && <> <button className="bk-more" onClick={() => save(claude ? { anthropic_key: '' } : { openai_api_key: '' }, refresh)}>Remove the saved key</button></>}</p>
    </div>
  )
}

function LocalForm({ s, refresh }: { s: any; refresh: () => void }) {
  const [url, setUrl] = useState<string>(s?.settings?.openai_url ?? 'http://localhost:1234/v1')
  const [model, setModel] = useState<string>(s?.settings?.openai_model ?? '')
  const [ver, setVer] = useState(0)
  const [loading, setLoading] = useState<{ busy: boolean; msg: string; ok?: boolean }>({ busy: false, msg: '' })
  const local = useAsync(() => api.llmModels(url).then((r: any) => r.models ?? []).catch(() => []), [url, ver])
  const models: any[] = local.data ?? []
  useEffect(() => { const t = window.setInterval(() => setVer(v => v + 1), models.length ? 30000 : 5000); return () => window.clearInterval(t) }, [models.length])
  const target = models.find(m => m.id === model) ?? models.find(m => m.loaded) ?? models[0]
  const load = async () => {
    if (!target) return
    setLoading({ busy: true, msg: `Loading ${target.name ?? target.id} in LM Studio… big models can take a minute or two.` })
    try {
      const r: any = await api.llmLoad({ url, model: target.id, context_length: 32768, unload_others: true })
      if (!r.ok) { setLoading({ busy: false, msg: r.error, ok: false }); return }
      setModel(target.id)
      await api.llmSettings({ openai_url: url, openai_model: target.id })
      setLoading({ busy: false, msg: `✓ Loaded ${target.id} with a ${(r.context ?? 32768).toLocaleString()}-token window.`, ok: true })
      setVer(v => v + 1); refresh()
    } catch (e: any) { setLoading({ busy: false, msg: String(e?.message ?? e), ok: false }) }
  }
  return (
    <div className="ai-connect">
      <Found ok={models.length > 0}>{models.length ? <>LM Studio is answering at {url}: {models.length} model{models.length === 1 ? '' : 's'} to choose from.</> : <>Nothing is answering at {url} yet. This page keeps looking.</>}</Found>
      <ol className="ai-steps">
        <li>Install <b>LM Studio</b> from <a href="https://lmstudio.ai" target="_blank" rel="noreferrer">lmstudio.ai</a> and open it.</li>
        <li>In its <b>Discover</b> (search) tab, download a model. Bigger follows the instructions better: about 12–14B for a graphics card with 8–12 GB, 27–32B for 24 GB. Models under 8B often fail.</li>
        <li>In its <b>Developer</b> tab, switch <b>Start server</b> on. It should say it's running at <code>http://localhost:1234</code>.</li>
        <li>Pick the model here and press <b>Load</b>: the simulator loads it with a big enough memory (context window) and saves your choice.</li>
      </ol>
      <ModelRow label="Model">
        <select value={target?.id ?? ''} onChange={e => { setModel(e.target.value); save({ openai_url: url, openai_model: e.target.value }, refresh) }} disabled={!models.length}>
          {!models.length && <option value="">no models yet</option>}
          {models.map(m => <option key={m.id} value={m.id}>{m.name ?? m.id}{m.params ? ` · ${m.params}` : ''}{m.loaded ? ' · loaded' : ''}</option>)}
        </select>
        <button className="btn small primary" disabled={!target || loading.busy} onClick={load}>{loading.busy ? 'Loading…' : 'Load'}</button>
      </ModelRow>
      {loading.msg && <p className={loading.ok === false ? 'ai-warn' : 'ai-note'}>{loading.msg}</p>}
      <details className="ai-more"><summary>Using Ollama or another server?</summary>
        <p className="ai-note">Ollama: run <code>ollama pull</code> with a model name, then use <code>http://localhost:11434/v1</code>.</p>
        <ModelRow label="Server"><input type="text" value={url} onChange={e => setUrl(e.target.value)} onBlur={() => save({ openai_url: url }, refresh)} style={{ flex: 1 }} /></ModelRow>
      </details>
    </div>
  )
}

// ---------------------------------------------------------------- step 3: test
function Test({ b, onDone, auto, onChange }: { b: Backend; onDone: () => void; auto: boolean; onChange: () => void }) {
  const [r, setR] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true); setR(null)
    try { setR(await api.llmTest()) } catch (e: any) { setR({ ok: false, error: String(e?.message ?? e) }) }
    setBusy(false)
  }
  useEffect(() => { if (auto) run() }, [])   // only right after connecting: each test uses a little of the plan or credit
  return (
    <div className="ai-test">
      {!busy && !r && <p className="ai-found">Using <b>{BACKEND_NAME[b]}</b>. Press <b>Test the connection</b> to check that it answers (uses a tiny bit of your plan or credit).</p>}
      {busy && <p className="ai-found">… Asking {BACKEND_NAME[b]} to say one word. This can take up to a minute the first time.</p>}
      {r?.ok && <>
        <p className="ai-found ok big">✓ Connected. It replied "{r.reply}" in {r.seconds} s.</p>
        <p className="ai-note">You're set. Open <b>What-if</b> and describe an idea in plain words; the AI proposes exact changes and shows them to you before anything runs.</p>
      </>}
      {r && !r.ok && <>
        <p className="ai-found warn big">✕ Not working yet.</p>
        <p className="ai-warn">{r.error}</p>
        {r.hint && <p className="ai-note"><b>What to do:</b> {r.hint}</p>}
      </>}
      <div className="ai-row">
        <button className={`btn small ${r ? '' : 'primary'}`} disabled={busy} onClick={run}>{busy ? 'Testing…' : r ? 'Test again' : 'Test the connection'}</button>
        <button className="btn small ghost" onClick={onChange}>Change the AI</button>
        <span className="spacer" />
        {r?.ok && <button className="btn primary" onClick={onDone}>Done</button>}
      </div>
      <p className="ai-note">Stuck? Give the file <code>docs/AI_SETUP_GUIDE.md</code> from the simulator's GitHub page to any AI assistant and ask it to walk you through this.</p>
    </div>
  )
}

// ---------------------------------------------------------------- the dialog
export function AiSetup() {
  const { open, hide, bump } = useAiSetup()
  const st = useAiStatus()
  const s: any = st.data
  const [step, setStep] = useState<0 | 1 | 2>(0)
  const [b, setB] = useState<Backend | null>(null)
  const [auto, setAuto] = useState(false)
  useEffect(() => { if (open) { setStep(s?.ready ? 2 : 0); setB(s?.settings?.backend ?? null); setAuto(false) } }, [open])
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') hide() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [open])
  if (!open || STATIC) return null
  const pick = async (x: Backend) => { setB(x); await api.llmSettings({ backend: x }); bump(); setStep(1) }
  const steps = ['Choose', 'Connect', 'Test']
  return (
    <div className="ai-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) hide() }}>
      <div className="ai-dialog card" role="dialog" aria-label="Connect an AI">
        <div className="ai-head">
          <b>Connect an AI</b>
          <div className="ai-crumbs">{steps.map((t, k) => (
            <button key={t} className={`${k === step ? 'on' : ''} ${k < step ? 'done' : ''}`} disabled={k > 0 && !b} onClick={() => setStep(k as 0 | 1 | 2)}>
              <i>{k < step ? '✓' : k + 1}</i>{t}</button>
          ))}</div>
          <button className="bx-icon" onClick={hide} aria-label="Close">{G.close}</button>
        </div>
        <div className="ai-body">
          {step === 0 && <Choose current={b ?? undefined} pick={pick} />}
          {step === 1 && b && <>
            <p className="ai-lede"><b>{BACKEND_NAME[b]}</b> <button className="bk-more" onClick={() => setStep(0)}>choose another</button></p>
            <Connect b={b} s={s} refresh={bump} checking={st.loading} />
          </>}
          {step === 2 && b && <Test key={`${b}-${auto}`} b={b} auto={auto} onDone={hide} onChange={() => setStep(0)} />}
        </div>
        {step === 1 && <div className="ai-foot"><button className="btn ghost" onClick={() => setStep(0)}>Back</button><span className="spacer" /><button className="btn primary" onClick={() => { setAuto(true); setStep(2) }}>Next: test it</button></div>}
      </div>
    </div>
  )
}
