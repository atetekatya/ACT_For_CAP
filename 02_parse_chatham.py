"""
02_parse_chatham.py
Downloads and parses the Chatham University course catalog PDF:
  https://www.chatham.edu/_documents/_academics/catalogs/chatham-university-catalog-2025-2026.pdf

Outputs: data/processed/Chatham_courses.json

NOTE: If the PDF download fails, place the file manually at:
  data/raw/Chatham_catalog.pdf
and re-run.
"""

import json, re, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdf_utils import download_pdf, extract_text_from_pdf

PDF_URL  = "https://www.chatham.edu/_documents/_academics/catalogs/chatham-university-catalog-2025-2026.pdf"
PDF_PATH = "data/raw/Chatham_catalog.pdf"
OUT_PATH = "data/processed/Chatham_courses.json"


# Course header: DEPT###[suffix] Title (credits)
# pdfminer often produces no separator between the previous block (department
# header, page footer) and the course code — so we don't anchor at line start.
COURSE_HEADER_RE = re.compile(
    r'([A-Z]{2,6})(\d{3,4}[A-Z]?)\s+'        # CODE (no space between letters and digits)
    r'([A-Za-z][^()\n]{2,140}?)'              # title (lazy, no parens or newlines)
    r'\s*\((\d+(?:\.\d+)?)\)'                 # (credits)
)
DEPT_HEADER_RE = re.compile(
    r'([A-Z]{2,6}):\s+([A-Z][A-Z &,/.\-]+?)(?=[A-Z]{2,6}\d{3,4}|[a-z])'
)
PAGE_FOOTER_RE = re.compile(
    r'(?:COURSE\s*DESCRIPTIONS?)?\s*CHATHAM\s+UNIVERSITY\s+CATALOG[:\s]*\d{4}-\d{4}\s*\d+',
    re.IGNORECASE
)
DESC_CAP = 4000


def parse_courses(text: str) -> list[dict]:
    """
    Scan-based parser for the Chatham catalog. Course headers can appear anywhere
    in the extracted text (not just at line starts) because pdfminer concatenates
    department headers and page footers without separators. We locate every header
    via finditer; the text between consecutive headers is the previous course's
    description.
    """
    anchor = re.search(r'COURSE\s*DESCRIPTIONS?', text, re.IGNORECASE)
    if anchor:
        body = text[anchor.end():]
    else:
        print("⚠️  'COURSE DESCRIPTIONS' anchor not found — scanning full text")
        body = text

    # Sorted list of (position, dept_code, dept_name) so each course can be
    # attributed to the most-recent department header preceding it.
    dept_positions = [
        (m.start(), m.group(1), m.group(2).strip())
        for m in DEPT_HEADER_RE.finditer(body)
    ]

    def dept_at(pos: int):
        active = ("", "")
        for p, code, name in dept_positions:
            if p <= pos:
                active = (code, name)
            else:
                break
        return active

    matches = list(COURSE_HEADER_RE.finditer(body))
    courses = []
    for idx, m in enumerate(matches):
        dept_code = m.group(1)
        num       = m.group(2)
        title     = m.group(3).strip(" -:.")
        credits   = m.group(4)

        desc_start = m.end()
        desc_end   = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        desc = body[desc_start:desc_end]

        desc = PAGE_FOOTER_RE.sub(' ', desc)
        desc = re.sub(r'[^\x20-\x7E -ɏ]', ' ', desc)
        desc = re.sub(r'\s+', ' ', desc).strip()
        if len(desc) > DESC_CAP:
            desc = desc[:DESC_CAP].rsplit(' ', 1)[0] + ' ...'

        dept, dept_name = dept_at(m.start())
        if not dept:
            dept = dept_code

        courses.append({
            "institution":     "Chatham University",
            "course_code":     f"{dept_code} {num}",
            "course_title":    title,
            "description":     desc,
            "credits":         credits,
            "department":      dept,
            "department_name": dept_name,
            "active":          True,
        })

    return courses


def main():
    os.makedirs("data/raw",       exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    if not download_pdf(PDF_URL, PDF_PATH):
        print("⚠️  PDF not available. Place it manually at:", PDF_PATH)
        with open(OUT_PATH, "w") as f:
            json.dump([], f)
        return

    print("Extracting text from Chatham PDF...")
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

    print(f"[Chatham] {len(courses)} courses → {OUT_PATH}")


if __name__ == "__main__":
    main()
