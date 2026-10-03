"""Build ucsim/config/majors.yaml: real BYU and UVU majors mapped to colleges and survey study areas.

Sources
  BYU: University Advisement, "Majors List by Colleges & Departments 2025-2026" (PDF, universityadvisement.byu.edu).
       Transcribed below (emphases collapsed into their major; second-major-only programs omitted).
  UVU: Academic Catalog "Find Your Program" (catalog.uvu.edu/programs), parsed into
       ucsim/config/sources/uvu_programs_catalog_2026.json (degree names only).
Weights are rough relative popularity within a study area (approximate); the study area itself is
drawn from the survey's per-school shares, so weights only split an area among its majors.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# (major, college, study area, weight, limited-enrollment)
B, E, CP, NU, LS, H, KC, FH, FA, ED = ("Marriott School of Business", "Fulton College of Engineering",
    "College of Computational, Mathematical & Physical Sciences", "College of Nursing", "College of Life Sciences",
    "College of Humanities", "Kennedy Center for International Studies", "College of Family, Home & Social Sciences",
    "College of Fine Arts & Communications", "McKay School of Education")
BYU = [
    ("Accounting", B, "Business", 4, True), ("Experience Design and Management", B, "Business", 1, True), ("Finance", B, "Business", 3, True),
    ("Information Systems", B, "Business", 2, True), ("Entrepreneurial Management", B, "Business", 2, True), ("Human Resource Management", B, "Business", 1, True),
    ("Strategic Management", B, "Business", 2, True), ("Global Supply Chain Management", B, "Business", 1, True), ("Marketing", B, "Business", 2, True),
    ("Chemical Engineering", E, "Engineering & Tech", 1, False), ("Civil Engineering", E, "Engineering & Tech", 2, False),
    ("Construction Management", E, "Engineering & Tech", 1, False), ("Facility and Property Management", E, "Engineering & Tech", 1, False),
    ("Computer Engineering", E, "Engineering & Tech", 2, False), ("Cybersecurity", E, "Engineering & Tech", 1, False), ("Electrical Engineering", E, "Engineering & Tech", 2, False),
    ("Manufacturing Engineering", E, "Engineering & Tech", 1, False), ("Mechanical Engineering", E, "Engineering & Tech", 3, True),
    ("Technology & Engineering Studies", E, "Engineering & Tech", 1, False),
    ("Computer Science", CP, "Engineering & Tech", 4, False), ("Computer Science: Animation and Games", CP, "Engineering & Tech", 1, True),
    ("Computer Science: Bioinformatics", CP, "Engineering & Tech", 1, False), ("Computer Science: Human-Computer Interaction", CP, "Engineering & Tech", 1, False),
    ("Computer Science: Software Engineering", CP, "Engineering & Tech", 2, False), ("Machine Learning", CP, "Math & Stats", 1, False),
    ("Biochemistry", CP, "Natural Sciences", 2, False), ("Chemistry", CP, "Natural Sciences", 1, False), ("Chemistry Education", CP, "Education", 1, False),
    ("Earth & Space Science Education", CP, "Education", 1, False), ("Environmental Geology", CP, "Agriculture & Environment", 1, False), ("Geology", CP, "Natural Sciences", 1, False),
    ("Mathematics", CP, "Math & Stats", 2, False), ("Applied & Computational Mathematics", CP, "Math & Stats", 2, False), ("Mathematics Education", CP, "Education", 2, False),
    ("Physical Science Education", CP, "Education", 1, False), ("Applied Physics", CP, "Natural Sciences", 1, False), ("Physics", CP, "Natural Sciences", 1, False),
    ("Physics and Astronomy", CP, "Natural Sciences", 1, False), ("Physics Education", CP, "Education", 1, False),
    ("Actuarial Science", CP, "Math & Stats", 1, False), ("Data Science", CP, "Math & Stats", 2, False), ("Statistics", CP, "Math & Stats", 2, False),
    ("Nursing", NU, "Health Sciences", 4, True),
    ("Biodiversity & Conservation", LS, "Agriculture & Environment", 1, False), ("Bioinformatics", LS, "Natural Sciences", 1, False),
    ("Biological Science Education", LS, "Education", 1, False), ("Biology", LS, "Natural Sciences", 3, False), ("Biophysics", LS, "Natural Sciences", 1, False),
    ("Cell Biology and Physiology", LS, "Health Sciences", 2, False), ("Exercise & Wellness", LS, "Health Sciences", 2, False), ("Exercise Science", LS, "Health Sciences", 5, False),
    ("Medical Laboratory Science", LS, "Health Sciences", 1, True), ("Microbiology", LS, "Natural Sciences", 1, False), ("Molecular Biology", LS, "Natural Sciences", 2, False),
    ("Neuroscience", LS, "Natural Sciences", 3, False), ("Dietetics", LS, "Health Sciences", 1, True), ("Food Science", LS, "Agriculture & Environment", 1, False),
    ("Nutritional Science", LS, "Health Sciences", 2, False), ("Environmental Science and Sustainability", LS, "Agriculture & Environment", 2, False),
    ("Genetics, Genomics & Biotechnology", LS, "Natural Sciences", 1, False), ("Plant and Landscape Systems", LS, "Agriculture & Environment", 1, False),
    ("Wildlife & Wildlands Conservation", LS, "Agriculture & Environment", 1, False), ("Public Health", LS, "Health Sciences", 4, False),
    ("Chinese", H, "Humanities", 1, False), ("Japanese", H, "Humanities", 1, False), ("Korean", H, "Humanities", 1, False),
    ("Art History & Curatorial Studies", H, "Humanities", 1, False), ("Classical Studies", H, "Humanities", 1, False), ("Comparative Literature", H, "Humanities", 1, False),
    ("Interdisciplinary Humanities", H, "Humanities", 1, False), ("Latin Teaching", H, "Education", 1, False), ("English", H, "Humanities", 3, False),
    ("English Teaching", H, "Education", 2, False), ("French", H, "Humanities", 1, False), ("French Teaching", H, "Education", 1, False), ("Italian", H, "Humanities", 1, False),
    ("German", H, "Humanities", 1, False), ("German Teaching", H, "Education", 1, False), ("Russian", H, "Humanities", 1, False),
    ("Applied English Linguistics", H, "Humanities", 1, False), ("Editing and Publishing", H, "Communications", 1, False), ("Linguistics", H, "Humanities", 1, False),
    ("Philosophy", H, "Humanities", 1, False), ("Portuguese", H, "Humanities", 1, False), ("Spanish", H, "Humanities", 2, False),
    ("Spanish Teaching", H, "Education", 1, True), ("Spanish Translation", H, "Humanities", 1, True), ("American Studies", H, "Humanities", 1, False),
    ("Ancient Near Eastern Studies", KC, "Humanities", 1, False), ("Asian Studies", KC, "Social Sciences", 1, False), ("European Studies", KC, "Social Sciences", 1, False),
    ("International Relations", KC, "Law & Policy", 2, False), ("Latin American Studies", KC, "Social Sciences", 1, False), ("Middle East Studies/Arabic", KC, "Social Sciences", 1, False),
    ("Anthropology", FH, "Social Sciences", 1, False), ("Economics", FH, "Social Sciences", 3, False), ("Family & Consumer Sciences Education", FH, "Education", 1, False),
    ("Family Studies", FH, "Social Sciences", 3, False), ("Human Development", FH, "Social Sciences", 2, False), ("Geography", FH, "Social Sciences", 1, False),
    ("Urban & Regional Planning (Geography)", FH, "Law & Policy", 1, False), ("Family History–Genealogy", FH, "Humanities", 1, False), ("History", FH, "Humanities", 2, False),
    ("History Teaching", FH, "Education", 1, False), ("Social Science Teaching", FH, "Education", 1, False), ("Political Science", FH, "Law & Policy", 3, False),
    ("Political Science: Legal Studies", FH, "Law & Policy", 1, False), ("Psychology", FH, "Social Sciences", 5, False), ("Sociology", FH, "Social Sciences", 2, False),
    ("Art", FA, "Fine Arts", 1, False), ("Art (BFA)", FA, "Fine Arts", 1, True), ("Art Education", FA, "Education", 1, True),
    ("Communications: Advertising", FA, "Communications", 2, True), ("Communications: Media & Society", FA, "Communications", 1, True),
    ("Communications: Journalism and Sports Media", FA, "Communications", 1, True), ("Communications: Public Relations", FA, "Communications", 2, True),
    ("Dance", FA, "Fine Arts", 1, False), ("Dance Education", FA, "Education", 1, True), ("Animation", FA, "Fine Arts", 1, True),
    ("Graphic Design", FA, "Fine Arts", 1, True), ("Illustration", FA, "Fine Arts", 1, True), ("Photo- & Lens-Based Design", FA, "Fine Arts", 1, True),
    ("Product & User Experience Design", FA, "Fine Arts", 1, True), ("Commercial Music", FA, "Fine Arts", 1, True), ("Music", FA, "Fine Arts", 1, False),
    ("Music Composition", FA, "Fine Arts", 1, True), ("Music Education", FA, "Education", 1, True), ("Music Performance", FA, "Fine Arts", 1, True),
    ("Acting", FA, "Fine Arts", 1, True), ("Media Arts Studies", FA, "Communications", 1, True), ("Music Dance Theatre", FA, "Fine Arts", 1, True),
    ("Theatre Arts Education", FA, "Education", 1, False), ("Theatre Arts Studies", FA, "Fine Arts", 1, False),
    ("Communication Disorders", ED, "Health Sciences", 2, True), ("Special Education", ED, "Education", 1, True),
    ("Early Childhood Education", ED, "Education", 2, False), ("Elementary Education", ED, "Education", 4, False),
    ("Physical Education Teaching/Coaching", ED, "Education", 1, False),
    ("Exploratory (undeclared)", "University Advisement Center", "Undeclared", 1, False),
]

UVU_COLLEGE = [  # first matching keyword wins
    (r"Account|Business|Financ|Marketing|Human Resource|Supply Chain|Hospitality|Event Management|Professional Sales|Strategic Foresight|Information Systems|Technology Management|International Business|Entrepreneur|Economics", "Woodbury School of Business"),
    (r"Engineer|Computer|Software|Cyber|Information Technology|Web Design|Construction|Aviation|Pilot|Digital Audio|Transportation|Mechatronics|Drafting|Welding|Automotive|Diesel|Electr", "Smith College of Engineering & Technology"),
    (r"Education|Teacher|Teaching", "School of Education"),
    (r"Nurs|Dental|Respiratory|Health|Exercise|Paramedic|Emergency|Criminal|Forensic|Occupational|Public Health|Outdoor Recreation|Fire|Medical|Culinary|Community Health", "College of Health & Public Service"),
    (r"Biolog|Botany|Zoology|Chem|Physics|Geology|Earth|Math|Statistic|Bioinformatics|Microbio|Biomedical|Biotech|Environmental|Data Science|Geography|Actuarial", "College of Science"),
    (r"Art|Dance|Music|Theatre|Animation|Cinema|Design|Photography|Illustration|Entertainment|Performance", "School of the Arts"),
    (r"Integrated Studies|Professional Advancement|General Studies|University Studies", "University College"),
]
UVU_AREA = [
    (r"Account|Business|Financ|Marketing|Human Resource|Supply Chain|Hospitality|Event Management|Professional Sales|Strategic Foresight|Information Systems|Technology Management|International Business|Entrepreneur", "Business"),
    (r"Education|Teacher|Teaching", "Education"),
    (r"Engineer|Computer|Software|Cyber|Information Technology|Web Design|Construction|Aviation|Pilot|Digital Audio|Transportation|Mechatronics|Drafting|Welding|Automotive|Diesel|Electr|Bioinformatics", "Engineering & Tech"),
    (r"Nurs|Dental|Respiratory|Health|Exercise|Paramedic|Occupational|Public Health|Medical|Biomedical", "Health Sciences"),
    (r"Math|Statistic|Actuarial|Data Science", "Math & Stats"),
    (r"Environmental|Botany|Outdoor Recreation|Wildland|Agricult|Geography", "Agriculture & Environment"),
    (r"Biolog|Zoology|Chem|Physics|Geology|Earth|Microbio|Biotech|Forensic", "Natural Sciences"),
    (r"Communication|Public Relations|Digital Marketing|Journalism", "Communications"),
    (r"Criminal|Political|National Security|Emergency|Legal|Paralegal|Fire", "Law & Policy"),
    (r"Art|Dance|Music|Theatre|Animation|Cinema|Design|Photography|Illustration|Entertainment|Performance", "Fine Arts"),
    (r"Psych|Sociology|Anthropology|Family|Social|Behavioral|Deaf Studies", "Social Sciences"),
    (r"English|History|Philosophy|Humanities|Spanish|Languages|Integrated Studies|Sign Language", "Humanities"),
    (r"General Studies|University Studies|Professional Advancement", "Undeclared"),
]
UVU_POPULAR = {"Nursing": 4, "Computer Science": 4, "Software Engineering": 3, "Psychology": 4, "Elementary Education": 3, "Accounting": 3,
               "Business Management": 4, "Marketing": 2, "Finance": 2, "Exercise Science": 3, "Criminal Justice": 2, "Information Technology": 2,
               "Professional Pilot": 2, "Dental Hygiene": 2, "Biology": 2, "Public Health": 2, "General Studies": 5, "Digital Cinema Production": 2,
               "Animation and Game Development": 2, "Communication": 2, "Applied Communication": 2, "Business and Analysis": 2}


def first(rules, name, default):
    for pat, val in rules:
        if re.search(pat, name):
            return val
    return default


def main():
    uvu_raw = json.loads((ROOT / "ucsim/config/sources/uvu_programs_catalog_2026.json").read_text(encoding="utf-8"))
    majors: dict[str, dict] = {}
    for p in uvu_raw:
        base = re.split(r" - ", p["name"])[0].strip()   # collapse emphases into the major
        assoc = p["degree"].startswith("A")
        m = majors.setdefault(base, {"major": base, "degrees": set(), "college": first(UVU_COLLEGE, base, "College of Humanities & Social Sciences"),
                                     "area": first(UVU_AREA, base, "Humanities")})
        m["degrees"].add(p["degree"])
        m["associate_only"] = m.get("associate_only", True) and assoc
    uvu = []
    for m in sorted(majors.values(), key=lambda r: r["major"]):
        uvu.append({"major": m["major"], "college": m["college"], "area": m["area"], "degrees": sorted(m["degrees"]),
                    "weight": UVU_POPULAR.get(m["major"], 1) * (0.6 if m["associate_only"] else 1.0)})
    byu = [{"major": n, "college": c, "area": a, "weight": w, "limited": lim} for n, c, a, w, lim in BYU]
    doc = {
        "sources": {
            "BYU": "BYU University Advisement, Majors List by Colleges & Departments 2025-2026 (PDF); emphases collapsed; second-major-only programs omitted",
            "UVU": "UVU Academic Catalog, Find Your Program (catalog.uvu.edu/programs), bachelor's and associate degrees; emphases collapsed",
            "weights": "approximate relative popularity within a study area (assumption)",
        },
        "BYU": byu, "UVU": uvu,
    }
    out = ROOT / "ucsim/config/majors.yaml"
    out.write_text("# Generated by scripts/build_majors.py — real BYU/UVU majors mapped to colleges and survey study areas.\n"
                   + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=140), encoding="utf-8")
    areas = {}
    for s in ("BYU", "UVU"):
        for m in doc[s]:
            areas.setdefault((s, m["area"]), 0)
            areas[(s, m["area"])] += 1
    print(f"wrote {out}: {len(byu)} BYU, {len(uvu)} UVU majors")
    print(sorted(areas.items()))


if __name__ == "__main__":
    main()
