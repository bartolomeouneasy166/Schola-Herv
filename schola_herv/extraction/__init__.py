"""
schola_herv.extraction
======================
PDF text-extraction utilities.

This module provides helpers for extracting raw text from downloaded PDFs
so you can feed them into downstream NLP / LLM pipelines.

Supported backends (imported lazily so hard dependencies are optional):
  - PyMuPDF  (``pymupdf`` / ``fitz``)  — fast, no extra install needed
  - pdfminer.six                        — install separately if preferred
  - MinerU / Grobid                     — external tools, call via subprocess

Quick usage
-----------
>>> from schola_herv.extraction import extract_text
>>> text = extract_text("paper.pdf")
>>> print(text[:200])
"""

from schola_herv.extraction.pdf import extract_text, batch_extract

__all__ = ["extract_text", "batch_extract"]
