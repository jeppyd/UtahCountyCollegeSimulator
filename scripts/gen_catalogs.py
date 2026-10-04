"""Generate docs/VARIABLE_CATALOG.md and docs/MECHANISMS.md from the YAML registries.

    python scripts/gen_catalogs.py
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from ucsim.registry import EVIDENCE_LEVELS, get_registry

ROOT = Path(__file__).resolve().parents[1]


def esc(s) -> str:
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def variables(reg) -> str:
    by = defaultdict(list)
    for k, v in reg.variables.items():
        by[(v.entity, v.domain)].append((k, v))
    counts = defaultdict(int)
    for v in reg.variables.values():
        counts[v.evidence] += 1
    out = ["# Variable catalog", "",
           "Generated from `ucsim/config/variables/*.yaml` by `scripts/gen_catalogs.py` — do not edit by hand.", "",
           f"{len(reg.variables)} variables. Evidence levels: " + ", ".join(f"**{k}** {counts[k]}" for k in EVIDENCE_LEVELS) + ".", "",
           "Columns: id · label · type (categories or range) · kind · update cadence · evidence · source · description.", ""]
    for (entity, domain), rows in sorted(by.items()):
        out += [f"## {entity} · {domain}", "", "| id | label | type | kind | update | evidence | source | description |", "|---|---|---|---|---|---|---|---|"]
        for k, v in rows:
            typ = f"cat: {', '.join(v.categories)}" if v.categories else f"{v.dtype}" + (f" [{v.range[0]}, {v.range[1]}]" if v.range else "")
            if v.units:
                typ += f" ({v.units})"
            out.append(f"| `{k}` | {esc(v.label)} | {esc(typ)} | {v.kind} | {v.update} | {v.evidence} | {esc(', '.join(v.source))} | {esc(v.desc)} |")
        out.append("")
    return "\n".join(out)


def mechanisms(reg) -> str:
    by = defaultdict(list)
    for m in reg.mechanisms.values():
        by[m.system].append(m)
    counts = defaultdict(int)
    for m in reg.mechanisms.values():
        counts[m.evidence] += 1
    out = ["# Mechanism registry", "",
           "Generated from `ucsim/config/mechanisms/*.yaml` and `events.yaml` by `scripts/gen_catalogs.py` — do not edit by hand.", "",
           f"{len(reg.mechanisms)} mechanisms. Evidence: " + ", ".join(f"**{k}** {counts[k]}" for k in EVIDENCE_LEVELS) + ".", "",
           "Every parameter can be overridden per run (`ParamSet`), targeted by an intervention (`target_type: param`) or swept.", "",
           "## Evidence levels", ""]
    for k, d in EVIDENCE_LEVELS.items():
        out.append(f"- **{k}** — {d}")
    out.append("")
    for sys_, ms in sorted(by.items()):
        out += [f"## {sys_}", ""]
        for m in ms:
            tg = m.target if isinstance(m.target, list) else [m.target]
            out += [f"### `{m.id}` — {m.label}", "",
                    f"*Evidence: {m.evidence} · timescale: {m.timescale} · delay: {m.delay}*", "",
                    f"- **Target**: {', '.join(f'`{t}`' for t in tg)}",
                    f"- **Inputs**: {', '.join(f'`{s}`' for s in m.sources) or '—'}"
                    + (f"; other inputs: {', '.join(m.context)}" if m.context else ""),
                    ]
            if m.moderators:
                out.append(f"- **Moderators**: {', '.join(f'`{s}`' for s in m.moderators)}")
            out.append(f"- **Form**: {m.form}")
            if m.params:
                out.append("- **Parameters**: " + "; ".join(
                    f"`{k}` = {v['value']}" + (f" (range {v['range'][0]}–{v['range'][1]})" if v.get("range") else "") for k, v in m.params.items()))
            if m.desc:
                out.append(f"- **Notes**: {m.desc}")
            if m.applicability:
                out.append(f"- **Applicability**: {m.applicability}")
            for r in m.refs:
                out.append(f"- *Ref*: {r}")
            out.append("")
    out += ["## Event types", "", "Events push states with decaying effects (half-life in days) and carry causal parent links.", "",
            "| event | category | salience | effects (var: magnitude, half-life d) | evidence |", "|---|---|---|---|---|"]
    for e in reg.events.values():
        eff = "; ".join(f"{x['var']}: {x['mag']:+g}, {x.get('half_life', '—')}" for x in e.effects)
        out.append(f"| `{e.id}` {esc(e.label)} | {e.category} | {e.salience} | {esc(eff)} | {e.evidence} |")
    return "\n".join(out) + "\n"


def main():
    reg = get_registry()
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "VARIABLE_CATALOG.md").write_text(variables(reg), encoding="utf-8")
    (ROOT / "docs" / "MECHANISMS.md").write_text(mechanisms(reg), encoding="utf-8")
    print("wrote docs/VARIABLE_CATALOG.md and docs/MECHANISMS.md")


if __name__ == "__main__":
    main()
