"""
PDF utility functions for Schola-herv.
"""

import re
from pathlib import Path


def verify_pdf(filepath: Path) -> bool:
    """
    Check if a file is a valid PDF by reading its magic bytes.
    
    Args:
        filepath: Path to the file.
        
    Returns:
        True if the file starts with %PDF, False otherwise.
    """
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
            return header == b'%PDF'
    except (IOError, OSError):
        return False


def generate_filename(metadata: dict) -> str:
    """
    Create a safe filename from paper metadata.
    
    The format is:
        Lastname1_Lastname2_Year_Title.pdf
    where the title is truncated and sanitized.
    
    Args:
        metadata: Dict with keys 'authors' (list), 'year', 'title'.
        
    Returns:
        A safe filename string ending with .pdf
    """
    # Authors: take up to 2 last names
    authors = metadata.get('authors', ['Unknown'])
    last_names = []
    for author in authors[:2]:
        # Take the last word of the author name as the last name
        parts = author.split()
        if parts:
            last_names.append(parts[-1])
    author_str = '_'.join(last_names) if last_names else 'Unknown'

    # Year
    year = metadata.get('year', 'unknown')

    # Title: clean and truncate
    title = metadata.get('title', 'untitled')
    # Keep only alphanumeric, spaces, underscores, hyphens
    title = re.sub(r'[^\w\s-]', '', title)
    title = title.strip().replace(' ', '_')
    # Limit length
    title = title[:80] if len(title) > 80 else title

    filename = f"{author_str}_{year}_{title}.pdf"
    # Remove any double underscores or trailing underscores
    filename = re.sub(r'_+', '_', filename)
    return filename