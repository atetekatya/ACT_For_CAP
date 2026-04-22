"""
06_build_database.py
Merges all per-institution JSON files into a single SQLite database:
  data/processed/act_for_cap.db

Schema
------
courses(
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  institution     TEXT NOT NULL,
  course_code     TEXT,
  course_title    TEXT,
  description     TEXT,
  credits         TEXT,
  department      TEXT,
  active          BOOLEAN DEFAULT 1
)

Also exports a combined CSV: data/processed/all_courses.csv
"""

import json, os, glob, sqlite3, csv

PROCESSED_DIR = "data/processed"
DB_PATH       = "data/processed/act_for_cap.db"
CSV_PATH      = "data/processed/all_courses.csv"

COLUMNS = ["institution", "course_code", "course_title",
           "description", "credits", "department", "active"]

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS courses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    institution TEXT NOT NULL,
    course_code TEXT,
    course_title TEXT,
    description TEXT,
    credits     TEXT,
    department  TEXT,
    active      BOOLEAN DEFAULT 1
);
"""

INSERT_SQL = """
INSERT INTO courses (institution, course_code, course_title,
                     description, credits, department, active)
VALUES (?, ?, ?, ?, ?, ?, ?);
"""


def load_json(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clean(val) -> str:
    """Normalize a value to string, stripping extra whitespace."""
    if val is None:
        return ""
    return str(val).strip()


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    # Collect all institution JSON files
    json_files = sorted(glob.glob(os.path.join(PROCESSED_DIR, "*_courses.json")))
    if not json_files:
        print("No processed JSON files found. Run the ingest/scrape scripts first.")
        return

    all_rows: list[tuple] = []
    for path in json_files:
        records = load_json(path)
        inst_name = os.path.basename(path).replace("_courses.json", "").replace("_", " ")
        print(f"  {inst_name}: {len(records)} records")
        for rec in records:
            row = (
                clean(rec.get("institution", inst_name)),
                clean(rec.get("course_code")),
                clean(rec.get("course_title")),
                clean(rec.get("description")),
                clean(rec.get("credits")),
                clean(rec.get("department")),
                1 if rec.get("active", True) else 0,
            )
            all_rows.append(row)

    # Build SQLite DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute(CREATE_SQL)

    # Index for fast querying
    cur.execute("CREATE INDEX IF NOT EXISTS idx_institution ON courses(institution);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_department  ON courses(department);")

    cur.executemany(INSERT_SQL, all_rows)
    conn.commit()

    total = cur.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    by_inst = cur.execute(
        "SELECT institution, COUNT(*) FROM courses GROUP BY institution ORDER BY institution"
    ).fetchall()

    conn.close()

    print(f"\n✅ Database built: {DB_PATH}")
    print(f"   Total rows: {total}")
    for inst, cnt in by_inst:
        print(f"   {inst}: {cnt}")

    # Export CSV
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id"] + COLUMNS)
        for i, row in enumerate(all_rows, start=1):
            writer.writerow([i] + list(row))

    print(f"\n✅ Combined CSV: {CSV_PATH}")


if __name__ == "__main__":
    main()
