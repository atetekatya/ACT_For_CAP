"""
run_pipeline.py
Master script for the ACT for CAP analysis pipeline.

Usage:
  python run_pipeline.py [--shu-only] [--skip-scrape] [--help]

Flags:
  --shu-only     Run SHU ingestion + analysis only (no peer scraping/PDF parsing)
  --skip-scrape  Skip scraping/parsing peers; use whatever peer data already exists
  --help         Print this message
"""

import subprocess, sys, os, argparse

STEPS = [
    ("01_ingest_shu.py",      "Ingest SHU catalog",                   False),
    ("02_parse_chatham.py",   "Parse Chatham University PDF catalog",  True),
    ("03_parse_pointpark.py", "Parse Point Park University PDF catalog", True),
    ("04_parse_stvincent.py", "Parse Saint Vincent College PDF",       True),
    ("05_parse_iup.py",       "Parse IUP PDF",                         True),
    ("06_build_database.py",  "Build SQLite database + combined CSV",  False),
    ("07_analyze.py",         "Run NLP analysis",                      False),
    ("08_report.py",          "Generate HTML report",                  False),
]

def run_step(script: str, label: str):
    print(f"\n{'─'*60}")
    print(f"▶  {label}")
    print(f"   Script: {script}")
    print(f"{'─'*60}")
    result = subprocess.run([sys.executable, script], capture_output=False)
    if result.returncode != 0:
        print(f"⚠️  {script} exited with code {result.returncode} — continuing anyway.")


def main():
    parser = argparse.ArgumentParser(description="ACT for CAP pipeline runner")
    parser.add_argument("--shu-only",    action="store_true",
                        help="Only run SHU ingestion and analysis (no peer scraping)")
    parser.add_argument("--skip-scrape", action="store_true",
                        help="Skip peer scraping/parsing; use existing peer data")
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs("data/raw",       exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)
    os.makedirs("output",         exist_ok=True)

    for script, label, is_peer in STEPS:
        if is_peer and (args.shu_only or args.skip_scrape):
            print(f"\n⏭  Skipping (peer step): {label}")
            continue
        run_step(script, label)

    print(f"\n{'='*60}")
    print("✅ Pipeline complete!")
    print(f"   Database:       data/processed/act_for_cap.db")
    print(f"   Combined CSV:   data/processed/all_courses.csv")
    print(f"   Redundancy:     output/shu_redundant_pairs.csv")
    print(f"   Cross-inst:     output/cross_institution_matches.csv")
    print(f"   Keywords:       output/keyword_frequencies.csv")
    print(f"   HTML Report:    output/ACT_for_CAP_Report.html")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()