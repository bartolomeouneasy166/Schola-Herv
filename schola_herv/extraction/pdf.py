"""
PDF text extraction using PyMuPDF (fitz).

Install: pip install pymupdf
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("schola_herv.extraction.pdf")


def extract_text(pdf_path: str | Path, min_length: int = 100) -> Optional[str]:
    """
    Extract plain text from a PDF file using PyMuPDF.

    Parameters
    ----------
    pdf_path : str or Path
        Path to the PDF file.
    min_length : int
        If the extracted text is shorter than this many characters, return None
        (likely a scanned/image-only PDF).

    Returns
    -------
    str or None
        Extracted text, or None if extraction failed or text is too short.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF is not installed. Run: pip install pymupdf")
        return None

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        logger.warning(f"PDF not found: {pdf_path}")
        return None

    try:
        doc = fitz.open(str(pdf_path))
        pages = [page.get_text() for page in doc]
        doc.close()
        full_text = "\n".join(pages).strip()
        if len(full_text) < min_length:
            logger.warning(f"Extracted text too short ({len(full_text)} chars): {pdf_path.name}")
            return None
        return full_text
    except Exception as exc:
        logger.error(f"Failed to extract text from {pdf_path.name}: {exc}")
        return None


def batch_extract(
    pdf_dir: str | Path,
    output_dir: Optional[str | Path] = None,
    min_length: int = 100,
) -> List[dict]:
    """
    Extract text from all PDFs in a directory.

    Parameters
    ----------
    pdf_dir : str or Path
        Directory containing PDF files.
    output_dir : str or Path, optional
        If given, write each extracted text as a ``.txt`` file here.
    min_length : int
        Minimum character count to consider a successful extraction.

    Returns
    -------
    list of dict
        Each entry: ``{"filename": str, "text": str | None}``.
    """
    pdf_dir = Path(pdf_dir)
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    logger.info(f"Extracting text from {len(pdfs)} PDFs in {pdf_dir}")

    for pdf_path in pdfs:
        text = extract_text(pdf_path, min_length=min_length)
        if text and output_dir:
            txt_path = output_dir / (pdf_path.stem + ".txt")
            txt_path.write_text(text, encoding="utf-8")
        results.append({"filename": pdf_path.name, "text": text})

    successful = sum(1 for r in results if r["text"])
    logger.info(f"Extraction complete: {successful}/{len(pdfs)} succeeded.")
    return results
