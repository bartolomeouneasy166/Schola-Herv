"""
Async download manager for Schola-herv.
"""

import asyncio
import os
from pathlib import Path
from typing import List, Optional

import aiohttp
from tqdm.asyncio import tqdm

from schola_herv.downloader.checkpoint import Checkpoint
from schola_herv.downloader.sources.arxiv import ArxivDownloader
from schola_herv.downloader.sources.unpaywall import UnpaywallDownloader
from schola_herv.downloader.sources.direct import DirectDownloader
from schola_herv.utils.logger import setup_logger

logger = setup_logger(__name__)


class DownloadManager:
    """
    Coordinates concurrent PDF downloads for a batch of papers.

    A single :class:`aiohttp.ClientSession` is created once per
    :meth:`download_papers` call and shared across all concurrent workers.
    """

    def __init__(
        self,
        output_dir: Path,
        max_concurrent: int = 10,
        retry_attempts: int = 5,
    ):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent
        self.retry_attempts = retry_attempts
        self.checkpoint = Checkpoint(self.output_dir / "checkpoint.json")
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Base downloaders (tried in order)
        self.downloaders = [
            ArxivDownloader(),
            UnpaywallDownloader(),
            DirectDownloader(),
        ]

        # Optional Sci-Hub fallback – disabled by default
        if os.environ.get("SCHOLAHERV_USE_SCIHUB", "").lower() == "true":
            try:
                from schola_herv.downloader.sources.scihub import SciHubDownloader
                self.downloaders.append(SciHubDownloader())
                logger.info("Sci-Hub fallback enabled (use responsibly).")
            except ImportError:
                logger.warning(
                    "Sci-Hub module not found – falling back to standard sources."
                )

    async def download_papers(self, papers: List[dict]) -> List[Path]:
        """
        Download PDFs for a list of paper metadata dicts.

        Creates a single shared :class:`aiohttp.ClientSession` for the entire
        batch, skips papers already recorded in the checkpoint, and reports
        progress via tqdm.

        Returns:
            List of successfully downloaded file paths.
        """
        from schola_herv.utils.network import make_session
        from schola_herv.config import load_config

        cfg = load_config()
        email = (
            (cfg.unpaywall.email if cfg and hasattr(cfg, "unpaywall") else None)
            or "your.email@example.com"
        )

        async with make_session(email=email, max_connections=self.max_concurrent) as session:
            tasks = []
            skipped = 0
            for paper in papers:
                identifier = Checkpoint.paper_identifier(paper)
                if self.checkpoint.is_downloaded(identifier):
                    skipped += 1
                    continue
                tasks.append(
                    asyncio.create_task(
                        self._download_one(session, paper, identifier)
                    )
                )

            if skipped:
                logger.info(f"Skipped {skipped} already-downloaded papers.")
            if not tasks:
                logger.info("All papers already downloaded.")
                return []

            downloaded: List[Path] = []
            for coro in tqdm.as_completed(
                tasks, desc="Downloading", unit="paper", total=len(tasks)
            ):
                result = await coro
                if result:
                    downloaded.append(result)

            return downloaded

    async def _download_one(
        self,
        session: aiohttp.ClientSession,
        paper: dict,
        identifier: str,
    ) -> Optional[Path]:
        """
        Try to download a single paper using the available downloaders.

        Retries on failure up to *retry_attempts* times with exponential
        back-off (2 ** attempt seconds).

        Args:
            session:    Shared aiohttp session (created once in
                        :meth:`download_papers`).
            paper:      Paper metadata dict.
            identifier: Stable string identifier for the checkpoint.

        Returns:
            Path to the downloaded PDF, or ``None`` if all attempts failed.
        """
        async with self.semaphore:
            for attempt in range(self.retry_attempts):
                for downloader in self.downloaders:
                    try:
                        if await downloader.can_handle(paper):
                            path = await downloader.download(
                                session, paper, self.output_dir
                            )
                            if path is not None:
                                self.checkpoint.mark_downloaded(identifier)
                                return path
                            # downloader claimed it could handle but failed; try next
                    except Exception as exc:
                        logger.warning(
                            f"Downloader {downloader.__class__.__name__} raised "
                            f"an unexpected error for '{identifier}' "
                            f"(attempt {attempt + 1}): {exc}",
                            exc_info=False,
                        )

                # All downloaders failed this attempt – wait before retry
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
                if attempt < self.retry_attempts - 1:
                    logger.debug(
                        f"All downloaders failed for '{identifier}' "
                        f"(attempt {attempt + 1}/{self.retry_attempts}). "
                        f"Retrying in {wait}s…"
                    )
                    await asyncio.sleep(wait)

            self.checkpoint.mark_failed(identifier)
            logger.warning(
                f"Failed after {self.retry_attempts} attempts: {identifier}"
            )
            return None
