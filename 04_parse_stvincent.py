"""
04_parse_stvincent.py
Downloads and parses the Saint Vincent College undergraduate catalog PDF:
  https://www.stvincent.edu/assets/docs/default-library/2025-2026-Catalog-Undergraduate-and-Graduate.pdf

Uses pdfminer.six for text extraction, then a scan-based heuristic parser
tailored to SVC's format:
  - Course codes: DEPT-NNN[suffix]   (e.g. AN-101, BL-150, MA-109)
  - Titles: ALL UPPERCASE, no separator before the description
  - Description starts at the first capital+lowercase pair after the title
  - Credits appear at the end of each description: "3 credits" or "3 credits."

Outputs: data/processed/StVincent_courses.json

NOTE: If the PDF download fails (network restrictions), place the PDF manually at:
  data/raw/StVincent_catalog.pdf
and re-run this script.
"""

import json, re, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdf_utils import download_pdf, extract_text_from_pdf

PDF_URL  = "https://www.stvincent.edu/assets/docs/default-library/2025-2026-Catalog-Undergraduate-and-Graduate.pdf"
PDF_PATH = "data/raw/StVincent_catalog.pdf"
OUT_PATH = "data/processed/StVincent_courses.json"


# Course header: DEPT-NNN[suffix] TITLE_IN_CAPS
# Title boundary: lazy match of uppercase letters / spaces / common punctuation,
# terminated by lookahead to a capital+lowercase pair (start of description) OR end.
COURSE_HEADER_RE = re.compile(
    r'([A-Z]{1,4})-(\d{3,4}[A-Z]?)\s+'           # CODE: AN-101, BL-150A, etc.
    r'([A-Z][A-Z0-9 \t\n&/.,;:\'"\-]+?)'          # TITLE: caps + symbols + whitespace, lazy
    r'\s*(?=[A-Z][a-z]|\Z)'                       # trailing ws + lookahead to sentence start
)
CREDIT_ANCHOR_RE = re.compile(
    r'\b(\d+(?:\.\d+)?)\s+credits?\b'
    r'|credits?\s*[:\-]\s*(\d+(?:\.\d+)?)'
    r'|\((\d+(?:\.\d+)?)\s*(?:credits?|cr)\)',
    re.IGNORECASE
)
SECTION_ANCHOR_RE = re.compile(r'Course\s+Descriptions?', re.IGNORECASE)
# Inside a title, this catches references to other courses (degree-audit
# listings). Real course titles have zero such references.
CODE_REF_IN_TITLE_RE = re.compile(r'\b[A-Z]{2,4}[\s\-]?\d{3,4}[A-Z]?\b')
DESC_CAP = 4000


def _find_section_start(text: str) -> int:
    """
    Return the offset of the first real course header inside the courses section.

    Strategy: walk every "Course Descriptions" occurrence from last to first.
    The actual section header is the latest mention that has a course-code
    pattern within ~500 chars after it (TOC entries don't). Page numbers and
    other layout junk between the heading and the first course are tolerated
    via the windowed search.
    """
    candidates = list(SECTION_ANCHOR_RE.finditer(text))
    for cand in reversed(candidates):
        window = text[cand.end():cand.end() + 500]
        first_course = COURSE_HEADER_RE.search(window)
        if first_course:
            return cand.end() + first_course.start()
    return -1


def _find_credits(s: str) -> str:
    m = CREDIT_ANCHOR_RE.search(s or "")
    if not m:
        return ""
    for g in m.groups():
        if g:
            return g
    return ""


def parse_courses(text: str, institution: str = "Saint Vincent College") -> list[dict]:
    """
    Scan-based SVC catalog parser.

    Anchors at "Course Descriptions" (immediately followed by a course code), then
    scans the body for every CODE-NNN TITLE pattern. The text between consecutive
    matches is the description for the previous course. Descriptions are capped
    at DESC_CAP characters.
    """
    start = _find_section_start(text)
    if start >= 0:
        body = text[start:]
        print(f"  Section start located at offset {start:,} — scanning {len(body):,} chars")
    else:
        body = text
        print("  ⚠️  Could not locate Course Descriptions section — scanning full text")

    matches = list(COURSE_HEADER_RE.finditer(body))
    print(f"  Found {len(matches)} course-header matches")

    courses = []
    skipped_audit = 0
    for idx, m in enumerate(matches):
        dept  = m.group(1)
        num   = m.group(2)
        title = re.sub(r'\s+', ' ', m.group(3)).strip(" -:.,;")

        # Drop degree-audit listings — real titles are English phrases, never a
        # list of course codes. Audit "titles" carry ≥2 code references.
        if len(CODE_REF_IN_TITLE_RE.findall(title)) >= 2:
            skipped_audit += 1
            continue

        desc_start = m.end()
        desc_end   = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        desc = body[desc_start:desc_end]

        # Normalize whitespace, drop control chars (keep Latin-1 punctuation)
        desc = re.sub(r'[^\x20-\x7E -ɏ]', ' ', desc)
        desc = re.sub(r'\s+', ' ', desc).strip()
        if len(desc) > DESC_CAP:
            desc = desc[:DESC_CAP].rsplit(' ', 1)[0] + ' ...'

        credits = _find_credits(desc) or _find_credits(title)

        courses.append({
            "institution":  institution,
            "course_code":  f"{dept}-{num}",
            "course_title": title,
            "description":  desc,
            "credits":      credits,
            "department":   dept,
            "active":       True,
        })

    if skipped_audit:
        print(f"  Filtered out {skipped_audit} degree-audit entries")
    return courses


def main():
    os.makedirs("data/raw", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    if not download_pdf(PDF_URL, PDF_PATH):
        print("⚠️  PDF not available. Place it manually at:", PDF_PATH)
        print("   Then re-run this script.")
        with open(OUT_PATH, "w") as f:
            json.dump([], f)
        return

    print("Extracting text from PDF (this may take a minute for large catalogs)...")
    try:
        text = extract_text_from_pdf(PDF_PATH)
    except Exception as e:
        print(f"✗ PDF text extraction failed: {e}")
        with open(OUT_PATH, "w") as f:
            json.dump([], f)
        return

    print(f"Extracted {len(text):,} characters of text. Parsing courses...")
    courses = parse_courses(text)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2, ensure_ascii=False)

    print(f"[Saint Vincent] {len(courses)} courses → {OUT_PATH}")


if __name__ == "__main__":
    main()
