"""
arXiv PDF downloader.

Handles papers whose ``source`` field is ``"arxiv"`` and that carry a
``pdf_url``.  arXiv serves PDFs with various content-types so we accept
both ``application/pdf`` and ``application/octet-stream``.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import aiohttp

from schola_herv.downloader.sources.base import BaseDownloader
from schola_herv.utils.pdf_utils import generate_filename, verify_pdf

logger = logging.getLogger("schola_herv.downloader.sources.arxiv")

_ACCEPTED_CONTENT_TYPES = {
    "application/pdf",
    "application/octet-stream",
    "binary/octet-stream",
}


class ArxivDownloader(BaseDownloader):
    """Download PDFs from arXiv using the direct ``pdf_url`` link."""

    async def can_handle(self, paper: dict) -> bool:
        return paper.get("source") == "arxiv" and bool(paper.get("pdf_url"))

    async def download(
        self,
        session: aiohttp.ClientSession,
        paper: dict,
        output_dir: Path,
    ) -> Optional[Path]:
        pdf_url = paper.get("pdf_url")
        if not pdf_url:
            return None

        filename = generate_filename(paper)
        filepath = output_dir / filename
        if filepath.exists() and verify_pdf(filepath):
            return filepath

        url_is_pdf = pdf_url.lower().endswith(".pdf")

        try:
            async with session.get(
                pdf_url,
                timeout=aiohttp.ClientTimeout(total=60, connect=10),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"ArxivDownloader: HTTP {resp.status} for {pdf_url}"
                    )
                    return None

                ct = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()

                if not url_is_pdf and ct not in _ACCEPTED_CONTENT_TYPES:
                    logger.warning(
                        f"ArxivDownloader: unexpected Content-Type '{ct}' for {pdf_url}"
                    )
                    return None

                content = await resp.read()
                filepath.write_bytes(content)
                if verify_pdf(filepath):
                    logger.debug(f"ArxivDownloader: saved {filepath.name}")
                    return filepath
                filepath.unlink(missing_ok=True)
                logger.warning(
                    f"ArxivDownloader: downloaded file failed PDF verification: {pdf_url}"
                )
                return None

        except asyncio.TimeoutError:
            logger.warning(f"ArxivDownloader: timeout for {pdf_url}")
        except aiohttp.ClientError as exc:
            logger.warning(f"ArxivDownloader: network error for {pdf_url}: {exc}")
        except Exception as exc:
            logger.warning(f"ArxivDownloader: unexpected error for {pdf_url}: {exc}")

        return None
