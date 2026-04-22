"""
01_ingest_shu.py
Ingests the SHU course catalog CSV and normalizes it into the shared schema:
  institution, course_code, course_title, description, credits, status
"""

import csv
import json
import re
import os

RAW_PATH = "data/raw/SHU_catalog.csv"
OUT_PATH  = "data/processed/SHU_courses.json"

# Regex to pull credit count from description field, e.g. "... 3 credits."
CREDIT_RE = re.compile(r'\b(\d+(?:\.\d+)?)\s+credit', re.IGNORECASE)

def extract_credits(description: str) -> str:
    """Pull the first credit count found in the description string."""
    if not description:
        return "" 
    m = CREDIT_RE.search(description)
    return m.group(1) if m else ""

def parse_department(course_code: str) -> str:
    """
    SHU codes look like 'SAR  101', 'SCS  215'.
    Department prefix = letters after leading 'S' (the 'S' is Seton Hill prefix).
    e.g. SAR → Art, SCS → Computer Science (we store raw prefix).
    """
    code = course_code.strip()
    # Extract alpha prefix, strip leading whitespace
    m = re.match(r'^([A-Z]+)', code)
    return m.group(1) if m else code

def main():
    courses = []
    with open(RAW_PATH, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code  = row.get("course code", "").strip()
            title = row.get("course title", "").strip()
            desc  = row.get("course description", "").strip()
            active = row.get("active status", "").strip().lower()

            if not code and not title:
                continue  # skip blank rows

            courses.append({
                "institution":   "Seton Hill University",
                "course_code":   code,
                "course_title":  title,
                "description":   desc,
                "credits":       extract_credits(desc),
                "department":    parse_department(code),
                "active":        active == "active",
            })

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2, ensure_ascii=False)

    active_count = sum(1 for c in courses if c["active"])
    print(f"[SHU] Loaded {len(courses)} courses ({active_count} active) → {OUT_PATH}")

if __name__ == "__main__":
    main()
