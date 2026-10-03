import { Evidence } from '../components'
import { useStore } from '../store'

const LAYERS: [string, string][] = [
  ['Population', 'Synthetic people drawn from survey-derived conditional tables and Gaussian copulas (within sex), calibrated to institutional totals. No agent is a survey respondent.'],
  ['Geography', 'Real Provo/Orem parcels, address points, buildings, LDS meetinghouses, parks and venues (Utah Geospatial Resource Center), plus named student complexes geocoded from OpenStreetMap.'],
  ['Schedules', 'Hourly day phases: classes, shifts, church, gym, gatherings, dates and venues chosen by obligation first, then a random-utility choice over drives (loneliness, stress, habits).'],
  ['Encounters', 'Co-presence in apartments, sections, wards, FHE groups, workplaces and venues creates meetings; similarity, chemistry and context set the valence of each contact.'],
  ['Relationships', 'Ties are first-class: contact hours, familiarity with forgetting (ACT-R), closeness and stage with hysteresis (Hall), plus directed attraction and the romance pipeline.'],
  ['Events', 'Every meaningful change is an event with a mechanism id and a causal parent, so any outcome can be traced back through its chain.'],
  ['States', 'Emotions are a setpoint plus additive mechanism terms plus decaying event effects plus noise — the decomposition you see under “why” is exact, not post-hoc.'],
  ['Interventions', 'World, parameter, agent and venue changes ramp in on a forked universe that shares random streams with the baseline, so differences are attributable to the change.'],
]

const LIMITS = [
  'Survey samples are convenience samples; married share, activity and other margins were re-weighted to institutional targets but residual bias remains.',
  'Variables from different surveys are linked through a copula on shared bridge variables — this assumes conditional independence given those bridges.',
  'Many mechanism strengths are calibrated or hypothetical. The evidence label on every mechanism says which; treat hypothetical ones as scenario assumptions.',
  'Sexuality, faith and mental health are modeled as probabilistic tendencies for aggregate exploration, never as predictions about any real person.',
  'The first iteration runs ~10–20k agents at reduced scale (default 30%); counts in the UI are scaled back to the full population where noted.',
  'Validation so far compares simulated distributions to survey targets (see VALIDATION.md); out-of-sample checks against administrative data are on the roadmap.',
]

export default function About() {
  const { registry, status } = useStore()
  const ev = registry!.evidence_levels
  const counts: Record<string, number> = {}
  for (const m of Object.values(registry!.mechanisms) as any[]) counts[m.evidence] = (counts[m.evidence] ?? 0) + 1
  return (
    <div className="page">
      <h1>About this model</h1>
      <p className="sub">An event-driven, spatial social microsimulation of the BYU/UVU college ecosystem in Provo and Orem. It is a laboratory for asking “what tends to happen, to whom, and why” — not a forecast about any individual.</p>
      <div className="grid g2">
        <div className="card">
          <h3>How it works</h3>
          <table className="data"><tbody>{LAYERS.map(([k, v]) => <tr key={k}><td style={{ whiteSpace: 'nowrap' }}><b>{k}</b></td><td className="small secondary">{v}</td></tr>)}</tbody></table>
        </div>
        <div className="card">
          <h3>Evidence levels</h3>
          <p className="hint">Every variable and mechanism carries one of these labels. Badges always show the word, not just a color.</p>
          <table className="data"><tbody>{Object.entries(ev).map(([k, v]) => (
            <tr key={k}><td><Evidence level={k} /></td><td className="small secondary">{v}</td><td className="tabular small muted">{counts[k] ?? 0} mech.</td></tr>
          ))}</tbody></table>
        </div>
        <div className="card">
          <h3>Data sources</h3>
          <ul className="small secondary" style={{ paddingLeft: 18 }}>
            <li>Four local student surveys (Provo stats, college life, dating, culture &amp; lifestyle) — used only as <b>aggregate</b> statistics with small cells (&lt;10) suppressed. Raw responses are not in the repository or this app.</li>
            <li>BYU / UVU enrollment and housing figures, LDS ward structure conventions, Utah wage and rent indices (configured in <code>world.yaml</code>).</li>
            <li>UGRC open GIS layers: parcels, buildings, address points, places of worship, parks, roads, municipal boundaries.</li>
            <li>OpenStreetMap / Nominatim for named apartment complexes; OpenFreeMap basemap tiles.</li>
            <li>Published research for mechanism forms (friendship hours, complex contagion, investment model, faith transitions, loneliness dynamics, etc.) — cited on each mechanism page.</li>
          </ul>
        </div>
        <div className="card">
          <h3>Limitations</h3>
          <ul className="small secondary" style={{ paddingLeft: 18 }}>{LIMITS.map(l => <li key={l}>{l}</li>)}</ul>
        </div>
        <div className="card">
          <h3>Privacy &amp; ethics</h3>
          <p className="small secondary">All people shown are synthetic. Names are generated from a hash of the agent index. No respondent record is reproduced or linkable, and the model never attempts to identify real individuals. Religious, sexual and mental-health characteristics are represented respectfully as probabilistic, multidimensional tendencies, to study aggregate patterns.</p>
        </div>
        <div className="card">
          <h3>This run</h3>
          <div className="small secondary">
            <div>Agents: <b className="tabular">{status.present?.toLocaleString?.() ?? "—"}</b> · scale {status.scale ?? '—'} · seed {status.seed ?? '—'}</div>
            <div>Registry: {Object.keys(registry!.variables).length} variables, {Object.keys(registry!.mechanisms).length} mechanisms, {Object.keys(registry!.events).length} event types.</div>
            <div style={{ marginTop: 6 }}>Docs in the repository: ARCHITECTURE, DATA_SOURCES, MODEL_ASSUMPTIONS, VARIABLE_CATALOG, MECHANISMS, VALIDATION, ROADMAP, DEVELOPMENT_LOG.</div>
          </div>
        </div>
      </div>
    </div>
  )
}
