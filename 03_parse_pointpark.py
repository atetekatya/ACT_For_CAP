"""
03_parse_pointpark.py
Downloads and parses the Point Park University course catalog PDF:
  https://www.pointpark.edu/about/admindepts/academicandstudent/universitycatalogs/point-park-undergrad-catalog.pdf

Outputs: data/processed/PointPark_courses.json

NOTE: If the PDF download fails, place the file manually at:
  data/raw/PointPark_catalog.pdf
and re-run.
"""

import json, re, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdf_utils import download_pdf, extract_text_from_pdf

PDF_URL  = "https://www.pointpark.edu/about/admindepts/academicandstudent/universitycatalogs/point-park-undergrad-catalog.pdf"
PDF_PATH = "data/raw/PointPark_catalog.pdf"
OUT_PATH = "data/processed/PointPark_courses.json"

CREDIT_RE = re.compile(r'\b(\d+(?:\.\d+)?)\s+[Cc]redit', re.IGNORECASE)


def parse_courses(text: str) -> list[dict]:
    courses = []
    lines = text.splitlines()

    current_code  = ""
    current_title = ""
    current_dept  = ""
    current_dept_name = ""
    desc_parts    = []
    credits = ""
    pending_course = False

    def flush():
        nonlocal current_code, current_title, current_dept, current_dept_name, desc_parts, credits, pending_course
        if current_title or current_code:
            desc = " ".join(desc_parts).strip()
            desc = re.sub(r'\s+', ' ', desc)
            desc = re.sub(r'[^\x20-\x7E\u00A0-\u024F]', ' ', desc)
            # Extract credits from description if present
            m = re.match(r'^(\d+(?:\.\d+)?)\s+[Cc]redits?\s*(.+)', desc)
            if m:
                credits = m.group(1)
                desc = m.group(2)
            courses.append({
                "institution":  "Point Park University",
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
        pending_course = False

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

        # Detect department header: e.g. "ACCT – ACCOUNTING"
        dept_match = re.match(r'^([A-Z]{2,6})\s*–\s*(.+)$', stripped)
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

        # Match course code line: e.g. "ACCT 210 Introduction to Financial Accounting"
        m = re.match(r'^([A-Z]{2,6})\s+(\d{3,4}[A-Z]?)\s+(.+)$', stripped)
        if m and in_courses_section:
            flush()
            dept          = m.group(1)
            num           = m.group(2)
            title         = m.group(3).strip()
            current_code  = f"{dept} {num}"
            current_title = title
            current_dept  = current_dept or dept
            pending_course = True
            i += 1
            # Check next line for credits
            if i < len(lines):
                next_stripped = lines[i].strip()
                cred_match = re.match(r'^(\d+(?:\.\d+)?)\s+[Cc]redits?', next_stripped)
                if cred_match:
                    credits = cred_match.group(1)
                    # Add the rest of the line as description
                    rest = next_stripped[len(cred_match.group(0)):].strip()
                    if rest:
                        desc_parts.append(rest)
                    i += 1
                else:
                    credits = ""
            else:
                credits = ""
            continue
        elif pending_course and in_courses_section:
            # Collect description lines
            if re.match(r'^\d+\s*$', stripped):
                i += 1
                continue
            # Removed len check
            desc_parts.append(stripped)
            i += 1
            continue

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

    print("Extracting text from Point Park PDF...")
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

    print(f"[Point Park] {len(courses)} courses → {OUT_PATH}")


if __name__ == "__main__":
    main()