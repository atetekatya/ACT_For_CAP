"""
05_parse_iup.py
Downloads and parses the Indiana University of Pennsylvania (IUP) undergraduate
catalog PDF:
  https://www.iup.edu/registrar/files/academic_catalogs/undergraduate-catalog-2024-2025-final.pdf

The IUP catalog uses a clean line-oriented layout. Each course block looks like:
    ACCT 200 - Foundations of Accounting
    Class Hours: 3
    Lab/Discussion: 0
    Credits: 3
    Prerequisite: ACCT 201           (optional)
    Description: <prose...>
    <continuation lines>
    ACCT 201 - Accounting Principles I   (next header → flushes the previous course)

So we use a small state machine over lines rather than a scan-based regex.

Outputs: data/processed/IUP_courses.json
"""

import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdf_utils import download_pdf, extract_text_from_pdf

PDF_URL  = "https://www.iup.edu/registrar/files/academic_catalogs/undergraduate-catalog-2024-2025-final.pdf"
PDF_PATH = "data/raw/IUP_catalog.pdf"
OUT_PATH = "data/processed/IUP_courses.json"


COURSE_HEADER_RE    = re.compile(r'^([A-Z]{2,6})\s+(\d{3,4}[A-Z]?)\s+-\s+(.+?)\s*$')
CREDITS_LINE_RE     = re.compile(r'^Credits:\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
DESCRIPTION_LINE_RE = re.compile(r'^Description:\s*(.*)$', re.IGNORECASE)
SECTION_ANCHOR_RE   = re.compile(r'^Course\s+Descriptions?\s*$', re.IGNORECASE)
# A standalone short title-case line (e.g. "Accounting", "Computer Science").
# Used to terminate a description without consuming the dept-name line as prose.
DEPT_LINE_RE = re.compile(r'^[A-Z][a-zA-Z][A-Za-z\s&\-]{1,48}$')

NOISE_RES = (
    re.compile(r'^Indiana\s+University\s+of\s+Pennsylvania.*Catalog', re.IGNORECASE),
    re.compile(r'^\d+\s*\|\s*P\s*a\s*g\s*e\s*$', re.IGNORECASE),
    re.compile(r'^\d+\s*$'),
)
DESC_CAP = 4000


def _find_section_start_line(lines: list[str]) -> int:
    """Return the index of the LAST 'Course Descriptions' line. -1 if none."""
    last = -1
    for i, line in enumerate(lines):
        if SECTION_ANCHOR_RE.match(line.strip()):
            last = i
    return last


def _is_noise(s: str) -> bool:
    return any(p.match(s) for p in NOISE_RES)


def parse_courses(text: str, institution: str = "Indiana University of Pennsylvania") -> list[dict]:
    lines = text.splitlines()
    start = _find_section_start_line(lines)
    if start == -1:
        print("  ⚠️  'Course Descriptions' section not found")
        return []
    print(f"  Section anchor at line {start:,} (of {len(lines):,})")

    courses: list[dict] = []
    current: dict | None = None
    in_description = False

    def flush():
        nonlocal current
        if current and current["code"] and current["desc_parts"]:
            desc = " ".join(current["desc_parts"])
            desc = re.sub(r"\s+", " ", desc).strip()
            if len(desc) > DESC_CAP:
                desc = desc[:DESC_CAP].rsplit(" ", 1)[0] + " ..."
            courses.append({
                "institution":  institution,
                "course_code":  current["code"],
                "course_title": current["title"],
                "description":  desc,
                "credits":      current["credits"],
                "department":   current["dept"],
                "active":       True,
            })
        current = None

    for line in lines[start + 1:]:
        stripped = line.strip()
        if not stripped or _is_noise(stripped):
            continue

        m = COURSE_HEADER_RE.match(stripped)
        if m:
            flush()
            current = {
                "code":       f"{m.group(1)} {m.group(2)}",
                "title":      m.group(3).strip(),
                "dept":       m.group(1),
                "credits":    "",
                "desc_parts": [],
            }
            in_description = False
            continue

        if not current:
            continue

        cm = CREDITS_LINE_RE.match(stripped)
        if cm:
            current["credits"] = cm.group(1)
            continue

        dm = DESCRIPTION_LINE_RE.match(stripped)
        if dm:
            in_description = True
            tail = dm.group(1).strip()
            if tail:
                current["desc_parts"].append(tail)
            continue

        if in_description:
            # Department-name line ends the current description without being
            # captured as prose (e.g. "Finance" between ACCT and FIN courses).
            if DEPT_LINE_RE.match(stripped):
                in_description = False
                continue
            current["desc_parts"].append(stripped)

    flush()
    print(f"  Parsed {len(courses)} courses")
    return courses


def main():
    os.makedirs("data/raw", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    if not download_pdf(PDF_URL, PDF_PATH):
        print("⚠️  IUP PDF not available. Place it manually at:", PDF_PATH)
        with open(OUT_PATH, "w") as f:
            json.dump([], f)
        return

    print("Extracting text from IUP PDF (may take several minutes for large catalogs)...")
    try:
        text = extract_text_from_pdf(PDF_PATH)
    except Exception as e:
        print(f"✗ PDF text extraction failed: {e}")
        with open(OUT_PATH, "w") as f:
            json.dump([], f)
        return

    print(f"Extracted {len(text):,} characters. Parsing courses...")
    courses = parse_courses(text)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2, ensure_ascii=False)

    print(f"[IUP] {len(courses)} courses → {OUT_PATH}")


if __name__ == "__main__":
    main()
