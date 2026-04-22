"""
05_parse_iup.py
Downloads and parses the Indiana University of Pennsylvania (IUP) undergraduate catalog PDF:
  https://www.iup.edu/registrar/files/academic_catalogs/undergraduate-catalog-2024-2025-final.pdf

Reuses the same heuristic PDF parser as 04_parse_stvincent.py.
Outputs: data/processed/IUP_courses.json

NOTE: If the PDF download fails, place the file manually at:
  data/raw/IUP_catalog.pdf
and re-run.
"""

import json, re, os, io, sys

# Reuse parser from 04_parse_stvincent
sys.path.insert(0, os.path.dirname(__file__))

from importlib import import_module
stvincent = import_module('04_parse_stvincent')
download_pdf, extract_text_from_pdf, parse_courses = stvincent.download_pdf, stvincent.extract_text_from_pdf, stvincent.parse_courses

PDF_URL  = "https://www.iup.edu/registrar/files/academic_catalogs/undergraduate-catalog-2024-2025-final.pdf"
PDF_PATH = "data/raw/IUP_catalog.pdf"
OUT_PATH = "data/processed/IUP_courses.json"


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
    courses = parse_courses(text, institution="Indiana University of Pennsylvania")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2, ensure_ascii=False)

    print(f"[IUP] {len(courses)} courses → {OUT_PATH}")


if __name__ == "__main__":
    main()
