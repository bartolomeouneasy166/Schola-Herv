"""
Journal filter – block or allow papers by journal name/ISSN.
"""

import csv
from pathlib import Path
from typing import List, Optional


def load_journal_list(csv_path: Path) -> List[str]:
    """Read journal names or ISSNs from a CSV file. Expects column 'journal_name' or 'issn'."""
    entries = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            val = (row.get('journal_name') or row.get('issn') or '').strip().lower()
            if val:
                entries.append(val)
    return entries


def filter_by_journal(
    papers: List[dict],
    csv_path: Optional[str],
    mode: str = "block"
) -> List[dict]:
    """
    Keep or remove papers based on journal name.
    mode = 'block' : remove papers whose journal (or any part of name) matches an entry.
    mode = 'allow' : keep only papers whose journal matches an entry.
    (Matching is case‑insensitive substring on the journal field.)
    """
    if not csv_path:
        return papers

    journal_entries = load_journal_list(Path(csv_path))
    if not journal_entries:
        return papers

    filtered = []
    for paper in papers:
        journal = (paper.get('journal') or '').lower()
        matched = any(entry in journal for entry in journal_entries)
        if mode == "block" and matched:
            continue   # remove
        if mode == "allow" and not matched:
            continue   # remove if not in allowed list
        filtered.append(paper)
    return filtered