"""
Tests for discovery utilities.

Run with:
    pytest tests/ -v
"""

import pytest
from schola_herv.harvester import _extract_dois


def test_extract_dois_from_text():
    """Should extract valid DOIs from free text."""
    text = "See paper doi:10.1103/PhysRevLett.116.061102 and also 10.1038/nature12345."
    dois = _extract_dois(text)
    assert "10.1103/PhysRevLett.116.061102" in dois
    assert "10.1038/nature12345" in dois


def test_extract_dois_empty_text():
    """Should return empty list for text with no DOIs."""
    dois = _extract_dois("no doi here at all")
    assert dois == []


def test_extract_dois_deduplication():
    """Should not return duplicate DOIs."""
    text = "10.1234/test 10.1234/test 10.1234/test"
    dois = _extract_dois(text)
    assert len(dois) == 1
