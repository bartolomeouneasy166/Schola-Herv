"""
Generic URL-based PDF downloader.

Downloads a PDF directly from a ``pdf_url`` field in the paper metadata.
This covers Unpaywall-enriched papers, CORE links, and any other source
that sets the ``pdf_url`` key.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import aiohttp

from schola_herv.downloader.sources.base import BaseDownloader
from schola_herv.utils.pdf_utils import generate_filename, verify_pdf

logger = logging.getLogger("schola_herv.downloader.sources.direct")

# Content-type values we treat as "this might be a PDF"
_PDF_CONTENT_TYPES = {
    "application/pdf",
    "application/octet-stream",
    "binary/octet-stream",
}


class UrlDownloader(BaseDownloader):
    """
    Download a PDF from the ``pdf_url`` field in paper metadata.

    Accepts any of the following content-types as a valid PDF response:
    ``application/pdf``, ``application/octet-stream``,
    ``binary/octet-stream``.  Additionally, if the URL itself ends with
    ``.pdf`` the content-type check is bypassed entirely.
    """

    async def can_handle(self, paper: dict) -> bool:
        return bool(paper.get("pdf_url"))

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
            ) as response:
                if response.status != 200:
                    logger.warning(
                        f"UrlDownloader: HTTP {response.status} for {pdf_url}"
                    )
                    return None

                ct = response.headers.get("Content-Type", "").split(";")[0].strip().lower()

                # If URL ends in .pdf we trust it regardless of Content-Type
                if not url_is_pdf and ct not in _PDF_CONTENT_TYPES:
                    logger.warning(
                        f"UrlDownloader: unexpected Content-Type '{ct}' for {pdf_url}"
                    )
                    return None

                content = await response.read()
                filepath.write_bytes(content)
                if verify_pdf(filepath):
                    logger.debug(f"UrlDownloader: saved {filepath.name}")
                    return filepath
                filepath.unlink(missing_ok=True)
                logger.warning(
                    f"UrlDownloader: downloaded file failed PDF verification: {pdf_url}"
                )
                return None

        except aiohttp.ClientError as exc:
            logger.warning(f"UrlDownloader: network error for {pdf_url}: {exc}")
        except asyncio.TimeoutError:
            logger.warning(f"UrlDownloader: timeout for {pdf_url}")
        except Exception as exc:
            logger.warning(f"UrlDownloader: unexpected error for {pdf_url}: {exc}")

        return None


# Backward-compatibility alias
DirectDownloader = UrlDownloader

__all__ = ["UrlDownloader", "DirectDownloader"]
