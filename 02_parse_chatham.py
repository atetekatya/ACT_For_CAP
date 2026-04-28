"""
02_parse_chatham.py
Downloads and parses the Chatham University course catalog PDF:
  https://www.chatham.edu/_documents/_academics/catalogs/chatham-university-catalog-2025-2026.pdf

Outputs: data/processed/Chatham_courses.json

NOTE: If the PDF download fails, place the file manually at:
  data/raw/Chatham_catalog.pdf
and re-run.
"""

import json, re, os, io
import requests
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams

PDF_URL  = "https://www.chatham.edu/_documents/_academics/catalogs/chatham-university-catalog-2025-2026.pdf"
PDF_PATH = "data/raw/Chatham_catalog.pdf"
OUT_PATH = "data/processed/Chatham_courses.json"

HEADERS   = {"User-Agent": "Mozilla/5.0 (academic research project)"}
CREDIT_RE = re.compile(r'\b(\d+(?:\.\d+)?)\s+[Cc]redit', re.IGNORECASE)


def download_pdf(url: str, dest: str) -> bool:
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
    output = io.StringIO()
    laparams = LAParams(line_margin=0.5, word_margin=0.1)
    with open(path, "rb") as f:
        extract_text_to_fp(f, output, laparams=laparams)
    return output.getvalue()


def parse_courses(text: str) -> list[dict]:
    courses = []
    lines = text.splitlines()

    current_code  = ""
    current_title = ""
    current_dept  = ""
    current_dept_name = ""
    desc_parts    = []
    credits = ""

    def flush():
        nonlocal current_code, current_title, current_dept, current_dept_name, desc_parts, credits
        if current_title or current_code:
            desc = " ".join(desc_parts).strip()
            desc = re.sub(r'\s+', ' ', desc)
            desc = re.sub(r'[^\x20-\x7E\u00A0-\u024F]', ' ', desc)
            courses.append({
                "institution":  "Chatham University",
                "course_code":  current_code,
                "course_title": current_title,
                "description":  desc,
                "credits":      credits,
                "department":   current_dept,
                "department_name": current_dept_name,
                "active":       True,
            })
        current_code  = ""
        current_title = ""
        current_dept  = ""
        current_dept_name = ""
        desc_parts    = []
        credits = ""

    in_courses_section = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        # Detect start of course listings section
        if re.match(r'^(Courses?|Course Descriptions?|Course Listings?)\s*$', stripped, re.I):
            in_courses_section = True
            i += 1
            continue

        # Detect department header: e.g. "ACT: Accounting"
        dept_match = re.match(r'^([A-Z]{2,6}):\s*(.+)$', stripped)
        if dept_match:
            flush()  # flush previous course if any
            current_dept = dept_match.group(1)
            current_dept_name = dept_match.group(2).strip()
            in_courses_section = True
            i += 1
            continue

        # Detect end of course listings
        if in_courses_section and re.match(
            r'^(Appendix|Index|Faculty|Administration|Financial|Academic Policies|Accreditation)',
            stripped, re.I
        ):
            in_courses_section = False
            i += 1
            continue

        if not in_courses_section:
            i += 1
            continue

        # Match full course line: code title (credits)
        m = re.match(r'^([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)\s+(.+?)\s*\((\d+(?:\.\d+)?)\)$', stripped)
        if m:
            flush()
            dept          = m.group(1)
            num           = m.group(2)
            title         = m.group(3).strip()
            credits_val   = m.group(4)
            current_code  = f"{dept} {num}"
            current_title = title
            credits       = credits_val
            if not current_dept:
                current_dept = dept
            i += 1
            # Collect description until next course or department
            while i < len(lines):
                next_line = lines[i]
                next_stripped = next_line.strip()
                if not next_stripped:
                    i += 1
                    continue
                if re.match(r'^([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)\s+(.+?)\s*\((\d+(?:\.\d+)?)\)$', next_stripped) or \
                   re.match(r'^([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)$', next_stripped) or \
                   re.match(r'^(.+?)\s*\((\d+(?:\.\d+)?)\)$', next_stripped) or \
                   re.match(r'^([A-Z]{2,6}):\s*(.+)$', next_stripped) or \
                   re.match(r'^(Appendix|Index|Faculty|Administration|Financial|Academic Policies|Accreditation)', next_stripped, re.I) or \
                   "CHATHAM UNIVERSITY CATALOG" in next_stripped or re.match(r'^\d+$', next_stripped):
                    break
                desc_parts.append(next_stripped)
                i += 1
            continue

        # Check for title (credits) line first, then code
        m_title = re.match(r'^(.+?)\s*\((\d+(?:\.\d+)?)\)$', stripped)
        if m_title:
            flush()
            title = m_title.group(1).strip()
            credits_val = m_title.group(2)
            current_title = title
            credits = credits_val
            i += 1
            if i < len(lines):
                next_line = lines[i]
                next_stripped = next_line.strip()
                m_code = re.match(r'^([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)$', next_stripped)
                if m_code:
                    dept = m_code.group(1)
                    num = m_code.group(2)
                    current_code = f"{dept} {num}"
                    if not current_dept:
                        current_dept = dept
                    i += 1
                    # Collect description
                    while i < len(lines):
                        next_line2 = lines[i]
                        next_stripped2 = next_line2.strip()
                        if not next_stripped2:
                            i += 1
                            continue
                        if re.match(r'^([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)\s+(.+?)\s*\((\d+(?:\.\d+)?)\)$', next_stripped2) or \
                           re.match(r'^([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)$', next_stripped2) or \
                           re.match(r'^(.+?)\s*\((\d+(?:\.\d+)?)\)$', next_stripped2) or \
                           re.match(r'^([A-Z]{2,6}):\s*(.+)$', next_stripped2) or \
                           re.match(r'^(Appendix|Index|Faculty|Administration|Financial|Academic Policies|Accreditation)', next_stripped2, re.I) or \
                           "CHATHAM UNIVERSITY CATALOG" in next_stripped2 or re.match(r'^\d+$', next_stripped2):
                            break
                        desc_parts.append(next_stripped2)
                        i += 1
                else:
                    # If not code, treat as description or skip
                    pass
            continue

        # Check for code only line
        m_code_only = re.match(r'^([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)$', stripped)
        if m_code_only:
            flush()
            dept = m_code_only.group(1)
            num = m_code_only.group(2)
            current_code = f"{dept} {num}"
            if not current_dept:
                current_dept = dept
            i += 1
            if i < len(lines):
                next_line = lines[i]
                next_stripped = next_line.strip()
                m_title_next = re.match(r'^(.+?)\s*\((\d+(?:\.\d+)?)\)$', next_stripped)
                if m_title_next:
                    title = m_title_next.group(1).strip()
                    credits_val = m_title_next.group(2)
                    current_title = title
                    credits = credits_val
                    i += 1
                    # Collect description
                    while i < len(lines):
                        next_line2 = lines[i]
                        next_stripped2 = next_line2.strip()
                        if not next_stripped2:
                            i += 1
                            continue
                        if re.match(r'^([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)\s+(.+?)\s*\((\d+(?:\.\d+)?)\)$', next_stripped2) or \
                           re.match(r'^([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)$', next_stripped2) or \
                           re.match(r'^(.+?)\s*\((\d+(?:\.\d+)?)\)$', next_stripped2) or \
                           re.match(r'^([A-Z]{2,6}):\s*(.+)$', next_stripped2) or \
                           re.match(r'^(Appendix|Index|Faculty|Administration|Financial|Academic Policies|Accreditation)', next_stripped2, re.I) or \
                           "CHATHAM UNIVERSITY CATALOG" in next_stripped2 or re.match(r'^\d+$', next_stripped2):
                            break
                        desc_parts.append(next_stripped2)
                        i += 1
                else:
                    # If not title, treat as description or skip
                    pass
            continue

        # If in courses section and have current course, add to description
        if current_code or current_title:
            if re.match(r'^\d+\s*$', stripped) or len(stripped) < 4 or "CHATHAM UNIVERSITY CATALOG" in stripped or re.match(r'^\d+$', stripped):
                i += 1
                continue
            desc_parts.append(stripped)

        i += 1

    flush()
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