"""
pdf_utils.py
Shared helpers for the catalog-parsing scripts (02–05).

  download_pdf(url, dest)        Downloads a PDF, validates magic bytes.
  extract_text_from_pdf(path)    Extracts text via pdfminer.six.
"""

import os
import io
import requests
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams

HEADERS = {"User-Agent": "Mozilla/5.0 (academic research project)"}


def download_pdf(url: str, dest: str) -> bool:
    """
    Download a PDF to dest. Skips download if a valid PDF is already present.
    Validates the %PDF- magic bytes after download — if a server returns an
    HTML error/login page (the common cause of silent failures), the file is
    deleted and we report the failure clearly instead of letting pdfminer
    blow up downstream.
    """
    if os.path.exists(dest):
        with open(dest, "rb") as f:
            if f.read(5).startswith(b"%PDF-"):
                print(f"  PDF already exists at {dest}, skipping download.")
                return True
        print(f"  ⚠️  File at {dest} is not a valid PDF — re-downloading.")
        os.remove(dest)

    print(f"  Downloading PDF from {url} ...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=120, stream=True, allow_redirects=True)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size_mb = os.path.getsize(dest) / 1e6
        with open(dest, "rb") as f:
            head = f.read(5)
        if not head.startswith(b"%PDF-"):
            os.remove(dest)
            print(f"  ✗ Downloaded {size_mb:.1f} MB but it's not a PDF "
                  f"(got {head!r} — likely an HTML error/login page).")
            print(f"     Place a real PDF manually at {dest} and re-run.")
            return False
        print(f"  Downloaded {size_mb:.1f} MB")
        return True
    except Exception as e:
        print(f"  ✗ Download failed: {e}")
        return False


def extract_text_from_pdf(path: str) -> str:
    """Extract all text from a PDF using pdfminer.six with sensible layout params."""
    output = io.StringIO()
    laparams = LAParams(line_margin=0.5, word_margin=0.1)
    with open(path, "rb") as f:
        extract_text_to_fp(f, output, laparams=laparams)
    return output.getvalue()
