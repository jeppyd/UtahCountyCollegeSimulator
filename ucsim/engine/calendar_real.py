"""The real Provo calendar: BYU's and UVU's terms, finals, holidays and breaks, football Saturdays, General Conference,
devotionals and festivals (config/calendar/*.yaml).

A year with its own file (2026_27.yaml: published dates with sources) is used as written; any other academic year
(August–July) is built from rules.yaml (basis: rule). Weekly items (devotionals) are added to every year. Everything
here is pure lookup: no random numbers, so paired worlds see the same calendar.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

CAL_DIR = Path(__file__).resolve().parent.parent / "config" / "calendar"
SCHOOLS = ("BYU", "UVU")


@dataclass(frozen=True)
class Term:
    school: str
    name: str
    start: dt.date           # first day of classes
    classes_end: dt.date     # last day of instruction
    finals_start: dt.date    # first day of the exam period (an exam-preparation day counts)
    finals_end: dt.date      # last exam: the term's last day
    basis: str = "rule"
    source: str | None = None


@dataclass
class Item:
    id: str
    label: str
    start: dt.date
    end: dt.date
    kind: str
    basis: str = "rule"
    time: str | None = None
    place: dict | None = None
    source: str | None = None
    note: str | None = None
    effects: dict = field(default_factory=dict)

    def on(self, d: dt.date) -> bool:
        return self.start <= d <= self.end

    def minutes(self) -> int | None:
        if not self.time:
            return None
        h, m = self.time.split(":")
        return int(h) * 60 + int(m)

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "start": str(self.start), "end": str(self.end), "kind": self.kind,
                "basis": self.basis, "time": self.time, "place": self.place, "source": self.source, "note": self.note,
                "effects": self.effects}


def _date(x) -> dt.date:
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x))


def academic_year(d: dt.date) -> int:
    """The academic year a date belongs to, by its fall year (2026 for Aug 2026 – Jul 2027)."""
    return d.year if d.month >= 8 else d.year - 1


class _Year:
    """One academic year: its terms (per school) and its dated items."""

    def __init__(self, y: int, rules: dict, real: dict | None):
        self.y = y
        self.terms: dict[str, list[Term]] = {s: [] for s in SCHOOLS}
        self.items: list[Item] = []
        if real is not None:
            self._from_real(real)
        else:
            self._from_rules(rules)
        self._weekly(rules)
        self.items.sort(key=lambda it: (it.start, it.minutes() or 0, it.id))

    # ---------------------------------------------------------------- a published year
    def _from_real(self, R: dict):
        src, places = R.get("sources", {}), R.get("places", {})
        for school, ts in R.get("terms", {}).items():
            for t in ts:
                self.terms[school].append(Term(school, t["name"], _date(t["classes"][0]), _date(t["classes"][1]),
                                               _date(t["finals"][0]), _date(t["finals"][1]), t.get("basis", "real"),
                                               src.get(t.get("source"), t.get("source"))))
        for it in R.get("items", []):
            d = it["date"]
            a, b = (_date(d[0]), _date(d[1])) if isinstance(d, list) else (_date(d), _date(d))
            pl = places.get(it["place"]) if isinstance(it.get("place"), str) else it.get("place")
            self.items.append(Item(it["id"], it["label"], a, b, it.get("kind", "other"), it.get("basis", "real"),
                                   it.get("time"), pl, src.get(it.get("source"), it.get("source")), it.get("note"),
                                   dict(it.get("effects") or {})))

    # ---------------------------------------------------------------- a year from rules
    def _resolve(self, r, terms: dict) -> dt.date:
        y = self.y
        if "fixed" in r:
            m, d = map(int, r["fixed"].split("-"))
            return dt.date(y if m >= 8 else y + 1, m, d)
        if "nth" in r:
            m, wd, n = r["nth"]
            yr = y if m >= 8 else y + 1
            if n > 0:
                first = dt.date(yr, m, 1)
                return first + dt.timedelta(days=(wd - first.weekday()) % 7 + 7 * (n - 1))
            last = (dt.date(yr + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
            return last - dt.timedelta(days=(last.weekday() - wd) % 7)
        if "on_or_after" in r:
            md, wd = r["on_or_after"]
            d0 = self._resolve({"fixed": md}, terms)
            return d0 + dt.timedelta(days=(wd - d0.weekday()) % 7)
        if "observed" in r:
            d0 = self._resolve({"fixed": r["observed"]}, terms)
            return d0 - dt.timedelta(days=1) if d0.weekday() == 5 else d0 + dt.timedelta(days=1) if d0.weekday() == 6 else d0
        if "stadium_of_fire" in r:
            d0 = self._resolve({"fixed": "07-04"}, terms)
            return d0 - dt.timedelta(days=1) if d0.weekday() == 6 else d0
        if "after" in r:
            a = r["after"]
            if "term" in a:
                school, name, fld = a["term"].split(".")
                base = getattr(terms[(school, name)], fld)
            else:
                base = self._resolve(a, terms)
            d = base + dt.timedelta(days=int(r.get("days", 0)))
            if "weekday" in r:
                d += dt.timedelta(days=(int(r["weekday"]) - d.weekday()) % 7)
            return d
        raise ValueError(f"calendar rule not understood: {r}")

    def _from_rules(self, rules: dict):
        terms: dict[tuple[str, str], Term] = {}
        for school, ts in rules["terms"].items():
            for t in ts:
                s = self._resolve(t["start"], terms)
                off = lambda k: s + dt.timedelta(days=int(t[k]))  # noqa: E731
                term = Term(school, t["name"], s, off("classes_end"), off("finals_start"), off("finals_end"), "rule")
                terms[(school, t["name"])] = term
                self.terms[school].append(term)
        self._rule_terms = terms
        places = rules.get("places", {})
        for it in rules.get("items", []):
            a = self._resolve(it["date"], terms)
            b = self._resolve(it["until"], terms) if "until" in it else a + dt.timedelta(days=int(it.get("days", 1)) - 1)
            pl = places.get(it["place"]) if isinstance(it.get("place"), str) else it.get("place")
            self.items.append(Item(it["id"], it["label"], a, b, it.get("kind", "other"), it.get("basis", "rule"),
                                   it.get("time"), pl, None, it.get("note"), dict(it.get("effects") or {})))

    # ---------------------------------------------------------------- weekly items
    def _weekly(self, rules: dict):
        places = rules.get("places", {})
        closed = {d for it in self.items if "BYU" in (it.effects.get("no_class") or [])
                  for d in _days(it.start, it.end)}
        for wk in rules.get("weekly", []):
            for ref in wk.get("terms", []):
                school, name = ref.split(".")
                t = next((t for t in self.terms[school] if t.name == name), None)
                if t is None:
                    continue
                d = t.start + dt.timedelta(days=(int(wk["weekday"]) - t.start.weekday()) % 7)
                while d <= t.classes_end:
                    if d not in closed:
                        pl = places.get(wk["place"]) if isinstance(wk.get("place"), str) else wk.get("place")
                        self.items.append(Item(f"{wk['id']}_{d.isoformat()}", wk["label"], d, d, wk.get("kind", "other"),
                                               wk.get("basis", "rule"), wk.get("time"), pl, wk.get("source"), wk.get("note"),
                                               dict(wk.get("effects") or {})))
                    d += dt.timedelta(days=7)


def _days(a: dt.date, b: dt.date):
    for k in range((b - a).days + 1):
        yield a + dt.timedelta(days=k)


class RealCalendar:
    """Lookups by date. Years are built on first use and kept."""

    def __init__(self, cal_dir: Path | str = CAL_DIR):
        cal_dir = Path(cal_dir)
        self.rules = yaml.safe_load((cal_dir / "rules.yaml").read_text())
        self.real: dict[int, dict] = {}
        for f in sorted(cal_dir.glob("[0-9][0-9][0-9][0-9]_[0-9][0-9].yaml")):
            self.real[int(f.name[:4])] = yaml.safe_load(f.read_text())
        self._years: dict[int, _Year] = {}
        self._day_items: dict[dt.date, list[Item]] = {}

    def year(self, y: int) -> _Year:
        if y not in self._years:
            self._years[y] = _Year(y, self.rules, self.real.get(y))
        return self._years[y]

    def _near(self, d: dt.date):
        """The academic years whose terms or items can touch this date (a summer term runs into August)."""
        y = academic_year(d)
        return (self.year(y - 1), self.year(y))

    # ---------------------------------------------------------------- terms
    def term_info(self, school: str, d: dt.date) -> Term | None:
        for Y in self._near(d):
            for t in Y.terms.get(school, []):
                if t.start <= d <= t.finals_end:
                    return t
        return None

    def term(self, school: str, d: dt.date) -> str | None:
        t = self.term_info(school, d)
        return t.name if t else None

    def in_finals(self, school: str, d: dt.date) -> bool:
        t = self.term_info(school, d)
        return bool(t and t.finals_start <= d <= t.finals_end)

    def in_classes(self, school: str, d: dt.date) -> bool:
        t = self.term_info(school, d)
        return bool(t and t.start <= d <= t.classes_end)

    def terms_between(self, a: dt.date, b: dt.date) -> list[Term]:
        out = []
        for y in range(academic_year(a) - 1, academic_year(b) + 1):
            out += [t for ts in self.year(y).terms.values() for t in ts if t.finals_end >= a and t.start <= b]
        return sorted(set(out), key=lambda t: (t.start, t.school))

    # ---------------------------------------------------------------- items
    def items_on(self, d: dt.date) -> list[Item]:
        if d not in self._day_items:
            if len(self._day_items) > 4000:
                self._day_items.clear()
            self._day_items[d] = [it for Y in self._near(d) for it in Y.items if it.on(d)]
        return self._day_items[d]

    def items_between(self, a: dt.date, b: dt.date) -> list[Item]:
        seen, out = set(), []
        for y in range(academic_year(a) - 1, academic_year(b) + 1):
            for it in self.year(y).items:
                if it.end >= a and it.start <= b and (it.id, it.start) not in seen:
                    seen.add((it.id, it.start))
                    out.append(it)
        return sorted(out, key=lambda it: (it.start, it.minutes() or 0, it.id))

    def no_class(self, school: str, d: dt.date) -> bool:
        """No classes at this school that day: outside its classes, a weekend, or a holiday or break."""
        if not self.in_classes(school, d) or d.weekday() == 6:
            return True
        return any(school in (it.effects.get("no_class") or []) for it in self.items_on(d))

    def holiday(self, d: dt.date) -> bool:
        return any(it.kind == "holiday" and it.effects.get("no_class") for it in self.items_on(d))

    def conference(self, d: dt.date) -> bool:
        return any(it.effects.get("conference") for it in self.items_on(d))

    def travel_home_likely(self, d: dt.date) -> bool:
        return any(it.effects.get("travel_home_likely") for it in self.items_on(d))


@lru_cache(maxsize=1)
def default_calendar() -> RealCalendar:
    return RealCalendar()
