"""
manual_entry_template.py
Use this script when web scraping or PDF parsing fails (the Plan B scenario from the proposal).

It provides a CSV template for manually entering course data for peer institutions,
then converts that CSV to the standard JSON format used by 06_build_database.py.

Usage:
  1. Fill out the CSV template at data/raw/manual_<institution>.csv
  2. Run: python manual_entry_template.py <institution_name> <csv_path>

Example:
  python manual_entry_template.py "Chatham University" data/raw/manual_chatham.csv
"""

import csv, json, sys, os, re

CREDIT_RE = re.compile(r'\b(\d+(?:\.\d+)?)\s+credit', re.IGNORECASE)

TEMPLATE_HEADERS = [
    "course_code",
    "course_title",
    "description",
    "credits",
    "department",
    "active",
]

SAMPLE_ROWS = [
    ["BUS 101", "Introduction to Business", "An overview of business fundamentals including management, marketing, and finance.", "3", "BUS", "True"],
    ["CS 110",  "Intro to Computer Science", "Fundamentals of programming and computational thinking.", "3", "CS", "True"],
    ["PSY 101", "General Psychology", "Survey of psychological theories, research methods, and applied areas.", "3", "PSY", "True"],
]


def create_template(institution: str, out_path: str):
    """Create a blank CSV template for manual data entry."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(TEMPLATE_HEADERS)
        writer.writerows(SAMPLE_ROWS)
    print(f"Template created at {out_path}")
    print(f"Fill it in and re-run: python manual_entry_template.py \"{institution}\" {out_path}")


def csv_to_json(institution: str, csv_path: str):
    """Convert a filled-in CSV to the standard JSON format."""
    out_path = f"data/processed/{institution.replace(' ', '_')}_courses.json"
    os.makedirs("data/processed", exist_ok=True)

    courses = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row.get("course_code", "").strip()
            desc = row.get("description", "").strip()
            courses.append({
                "institution":  institution,
                "course_code":  code,
                "course_title": row.get("course_title", "").strip(),
                "description":  desc,
                "credits":      row.get("credits") or (
                    (lambda m: m.group(1) if m else "")(CREDIT_RE.search(desc))
                ),
                "department":   row.get("department", "").strip() or (
                    re.match(r'^([A-Z]+)', code.upper()).group(1) if code else ""
                ),
                "active":       row.get("active", "True").strip().lower() not in ("false", "0", "no"),
            })

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2, ensure_ascii=False)

    print(f"✅ {len(courses)} courses saved → {out_path}")
    print(f"   Now run: python 06_build_database.py && python 07_analyze.py && python 08_report.py")


def main():
    if len(sys.argv) < 2:
        # No arguments: just create templates for all peers
        peers = {
            "Chatham University":                   "data/raw/manual_chatham.csv",
            "Point Park University":                "data/raw/manual_pointpark.csv",
            "Saint Vincent College":                "data/raw/manual_stvincent.csv",
            "Indiana University of Pennsylvania":   "data/raw/manual_iup.csv",
        }
        print("Creating blank templates for all peer institutions...\n")
        for inst, path in peers.items():
            create_template(inst, path)
        return

    institution = sys.argv[1]
    csv_path    = sys.argv[2] if len(sys.argv) > 2 else f"data/raw/manual_{institution.split()[0].lower()}.csv"

    if not os.path.exists(csv_path):
        create_template(institution, csv_path)
    else:
        csv_to_json(institution, csv_path)


if __name__ == "__main__":
    main()
