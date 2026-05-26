"""
PubMed Central (PMC) Open Access PDF downloader.

Uses the PMC OA Web Service to fetch free full-text PDFs.
API docs: https://www.ncbi.nlm.nih.gov/pmc/tools/oa-service/
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

import aiohttp

from schola_herv.downloader.sources.base import BaseDownloader
from schola_herv.utils.pdf_utils import generate_filename, verify_pdf

logger = logging.getLogger("schola_herv.downloader.sources.pmc")

PMC_OA_API = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
PMC_BASE   = "https://www.ncbi.nlm.nih.gov"


class PMCDownloader(BaseDownloader):
    """Download open-access PDFs from PubMed Central."""

    async def can_handle(self, paper: dict) -> bool:
        pmcid = paper.get("pmcid") or ""
        # Also check if the source field indicates pubmed/pmc
        source = (paper.get("source") or "").lower()
        return bool(pmcid) or source in ("pubmed", "pmc")

    async def download(
        self, session: aiohttp.ClientSession, paper: dict, output_dir: Path
    ) -> Optional[Path]:
        pmcid = paper.get("pmcid")
        if not pmcid:
            # Try to extract PMCID from identifiers
            ids = paper.get("identifiers", {})
            pmcid = ids.get("pmcid") or ids.get("pmc")
        if not pmcid:
            return None

        # Normalise: ensure PMC prefix
        if not str(pmcid).upper().startswith("PMC"):
            pmcid = f"PMC{pmcid}"

        filename = generate_filename(paper)
        filepath = output_dir / filename
        if filepath.exists() and verify_pdf(filepath):
            return filepath

        # Step 1: query OA service for download links
        try:
            async with session.get(
                PMC_OA_API,
                params={"id": pmcid, "format": "pdf"},
                timeout=aiohttp.ClientTimeout(total=30, connect=10),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"PMC OA API returned {resp.status} for {pmcid}")
                    return None
                xml = await resp.text()
        except asyncio.TimeoutError:
            logger.warning(f"Timeout querying PMC OA API for {pmcid}")
            return None
        except aiohttp.ClientError as exc:
            logger.warning(f"Network error querying PMC OA for {pmcid}: {exc}")
            return None

        # Step 2: parse PDF link from XML response
        pdf_url = _extract_pdf_url(xml)
        if not pdf_url:
            logger.debug(f"No PDF link found in PMC OA response for {pmcid}")
            return None

        # Step 3: download the PDF
        try:
            async with session.get(
                pdf_url,
                timeout=aiohttp.ClientTimeout(total=60, connect=10),
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"Failed to download PMC PDF from {pdf_url}: HTTP {resp.status}"
                    )
                    return None
                content = await resp.read()
                filepath.write_bytes(content)
                if verify_pdf(filepath):
                    logger.info(f"Downloaded PMC PDF: {filepath.name}")
                    return filepath
                filepath.unlink(missing_ok=True)
                return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout downloading PMC PDF for {pmcid}")
            return None
        except aiohttp.ClientError as exc:
            logger.warning(f"Network error downloading PMC PDF for {pmcid}: {exc}")
            return None
        except Exception as exc:
            logger.error(
                f"Unexpected error downloading PMC PDF for {pmcid}: {exc}",
                exc_info=True,
            )
            return None


def _extract_pdf_url(xml: str) -> Optional[str]:
    """Parse the PDF href from PMC OA XML response."""
    # Look for <link format="pdf" href="..."/>
    m = re.search(
        r'<link[^>]+format=["\']pdf["\'][^>]+href=["\']([^"\']+)["\']', xml
    )
    if m:
        url = m.group(1)
        if url.startswith("ftp://"):
            # Convert FTP to HTTPS equivalent (PMC supports both)
            url = url.replace("ftp://", "https://", 1)
        return url
    # Fallback: any href ending in .pdf
    m = re.search(r'href=["\']([^"\']+\.pdf)["\']', xml)
    return m.group(1) if m else None
