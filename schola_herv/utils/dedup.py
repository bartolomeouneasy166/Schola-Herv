"""
Paper deduplication utilities — single source of truth used by
harvester.py, cli.py, and webapp/app.py.
"""
from __future__ import annotations

import hashlib
import logging
from typing import List

logger = logging.getLogger("schola_herv.utils.dedup")


def deduplicate_papers(papers: List[dict]) -> List[dict]:
    """
    Remove duplicate papers from a list.

    Deduplication strategy (in order of priority):
    1. DOI — exact match (case-insensitive, stripped).
    2. Title — normalised lowercase, alphanumeric-only, with year.
       A short MD5 hash of the original title is appended to reduce
       false-positive collisions on similarly-truncated titles.

    Parameters
    ----------
    papers:
        List of paper metadata dicts.

    Returns
    -------
    List of unique papers, preserving original order.
    """
    seen_doi:   set[str] = set()
    seen_title: set[str] = set()
    unique:     List[dict] = []

    for paper in papers:
        doi = (paper.get("doi") or "").strip().lower()
        if doi:
            if doi in seen_doi:
                continue
            seen_doi.add(doi)
        else:
            title = (paper.get("title") or "").lower()
            year  = str(paper.get("year") or "")
            slug  = "".join(c for c in title if c.isalnum() or c == " ")[:80]
            h     = hashlib.md5(title.encode()).hexdigest()[:8]
            key   = f"{slug}_{year}_{h}"
            if key in seen_title:
                continue
            seen_title.add(key)
        unique.append(paper)

    removed = len(papers) - len(unique)
    if removed:
        logger.info(f"Deduplication: {len(papers)} → {len(unique)} papers ({removed} duplicates removed)")
    return unique
