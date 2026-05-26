"""
Tests for the Schola-herv download engine.

Run with:
    pytest tests/ -v
"""

import asyncio
from pathlib import Path

import pytest

from schola_herv.downloader.sources.direct import DirectDownloader
from schola_herv.downloader.checkpoint import Checkpoint


# ---------------------------------------------------------------------------
# DirectDownloader
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_direct_downloader_can_handle_with_pdf_url():
    """DirectDownloader should accept papers that have a pdf_url."""
    import aiohttp
    downloader = DirectDownloader()
    paper = {"title": "Test Paper", "pdf_url": "https://example.com/test.pdf"}
    async with aiohttp.ClientSession() as session:
        result = await downloader.can_handle(paper)
    assert result is True


@pytest.mark.asyncio
async def test_direct_downloader_rejects_without_pdf_url():
    """DirectDownloader should reject papers without a pdf_url."""
    import aiohttp
    downloader = DirectDownloader()
    paper = {"title": "Test Paper"}  # no pdf_url
    async with aiohttp.ClientSession() as session:
        result = await downloader.can_handle(paper)
    assert result is False


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------

def test_checkpoint_mark_and_check(tmp_path):
    """Checkpoint should persist downloaded state."""
    cp = Checkpoint(tmp_path / "checkpoint.json")
    identifier = "10.1234/test.doi"

    assert not cp.is_downloaded(identifier)
    cp.mark_downloaded(identifier)
    assert cp.is_downloaded(identifier)


def test_checkpoint_mark_failed(tmp_path):
    """Checkpoint should track failed downloads separately."""
    cp = Checkpoint(tmp_path / "checkpoint.json")
    identifier = "10.5678/fail.doi"

    cp.mark_failed(identifier)
    # Failed papers are not marked as downloaded
    assert not cp.is_downloaded(identifier)


def test_checkpoint_persists_across_instances(tmp_path):
    """Checkpoint data should be reloaded from disk."""
    path = tmp_path / "checkpoint.json"
    cp1 = Checkpoint(path)
    cp1.mark_downloaded("doi:test/1")

    # New instance reads from same file
    cp2 = Checkpoint(path)
    assert cp2.is_downloaded("doi:test/1")


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_extract_text_missing_file():
    """extract_text should return None for a non-existent file."""
    from schola_herv.extraction import extract_text
    result = extract_text("/tmp/nonexistent_schola_test.pdf")
    assert result is None
