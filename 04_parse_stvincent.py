"""
04_parse_stvincent.py
Downloads and parses the Saint Vincent College undergraduate catalog PDF:
  https://www.stvincent.edu/assets/docs/default-library/2025-2026-Catalog-Undergraduate-and-Graduate.pdf

Uses pdfminer.six for text extraction, then heuristic parsing.
Outputs: data/processed/StVincent_courses.json

NOTE: If the PDF download fails (network restrictions), place the PDF manually at:
  data/raw/StVincent_catalog.pdf
and re-run this script.
"""

import json, re, os, io
import requests
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams

PDF_URL  = "https://www.stvincent.edu/assets/docs/default-library/2025-2026-Catalog-Undergraduate-and-Graduate.pdf"
PDF_PATH = "data/raw/StVincent_catalog.pdf"
OUT_PATH = "data/processed/StVincent_courses.json"

HEADERS   = {"User-Agent": "Mozilla/5.0 (academic research project)"}
# Matches lines like:  "ART 101  Introduction to Art  3 credits"
# or block headings like "ART 101. Introduction to Art."
COURSE_HEADER_RE = re.compile(
    r'^([A-Z]{2,6})\s+(\d{3,4}[A-Z]?)[.\s]+(.+?)(?:\s+(\d+(?:\.\d+)?)\s+[Cc]redit)?\.?\s*$'
)
CREDIT_RE = re.compile(r'\b(\d+(?:\.\d+)?)\s+[Cc]redit', re.IGNORECASE)


def download_pdf(url: str, dest: str):
    """Download PDF to dest path if not already present."""
    if os.path.exists(dest):
        print(f"  PDF already exists at {dest}, skipping download.")
        return True
    print(f"  Downloading PDF from {url} ...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=120, stream=True)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size_mb = os.path.getsize(dest) / 1e6
        print(f"  Downloaded {size_mb:.1f} MB")
        return True
    except Exception as e:
        print(f"  ✗ Download failed: {e}")
        return False


def extract_text_from_pdf(path: str) -> str:
    """Extract all text from a PDF using pdfminer."""
    output = io.StringIO()
    laparams = LAParams(line_margin=0.5, word_margin=0.1)
    with open(path, "rb") as f:
        extract_text_to_fp(f, output, laparams=laparams)
    return output.getvalue()


def parse_courses(text: str, institution: str = "Saint Vincent College") -> list[dict]:
    """
    Heuristic parser for academic catalog text.
    Looks for lines that start with a course code pattern (3-6 uppercase letters + 3-4 digit number).
    Everything after that line until the next course code is treated as the description.
    """
    courses = []
    lines = text.splitlines()

    current_code  = ""
    current_title = ""
    current_dept  = ""
    desc_parts    = []

    def flush():
        nonlocal current_code, current_title, current_dept, desc_parts
        if current_title or current_code:
            desc = " ".join(desc_parts).strip()
            # Clean up common PDF artifacts
            desc = re.sub(r'\s+', ' ', desc)
            desc = re.sub(r'[^\x20-\x7E\u00A0-\u024F]', ' ', desc)
            courses.append({
                "institution":  institution,
                "course_code":  current_code,
                "course_title": current_title,
                "description":  desc,
                "credits":      extract_credits(current_title + " " + desc),
                "department":   current_dept,
                "active":       True,
            })
        current_code  = ""
        current_title = ""
        current_dept  = ""
        desc_parts    = []

    def extract_credits(text: str) -> str:
        m = CREDIT_RE.search(text or "")
        return m.group(1) if m else ""

    # Only process lines within the "Courses" section of the catalog
    in_courses_section = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect start of course listings section
        if re.match(r'^(Courses?|Course Descriptions?|Course Listings?)\s*$', stripped, re.I):
            in_courses_section = True
            continue

        # Detect chapter/section headers that signal end of course listings
        if in_courses_section and re.match(
            r'^(Appendix|Index|Faculty|Administration|Financial|Academic Policies|Accreditation)',
            stripped, re.I
        ):
            in_courses_section = False

        # Match course code line regardless of section (PDFs often lack clear section markers)
        m = re.match(r'^([A-Z]{2,6})\s{1,5}(\d{3,4}[A-Z]?)[.\s:–-]+(.{3,80})$', stripped)
        if m:
            flush()
            in_courses_section = True
            dept         = m.group(1)
            num          = m.group(2)
            rest         = m.group(3).strip(" .-()")
            current_code  = f"{dept} {num}"
            current_dept  = dept
            current_title = rest
        elif in_courses_section and current_code:
            # Continuation line — part of description
            # Skip obvious page headers/footers
            if re.match(r'^\d+\s*$', stripped):
                continue
            if len(stripped) < 4:
                continue
            desc_parts.append(stripped)

    flush()
    return courses


def main():
    os.makedirs("data/raw", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)

    # Try to download PDF
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
