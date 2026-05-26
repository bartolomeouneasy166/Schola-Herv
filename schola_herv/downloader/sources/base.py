"""
Base downloader interface.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import aiohttp


class BaseDownloader(ABC):
    """Interface that every source-specific PDF downloader must implement."""

    @abstractmethod
    async def can_handle(self, paper: dict) -> bool:
        """
        Return True if this downloader can handle the given paper.
        Typically checks `paper['source']` or presence of `paper['pdf_url']`.
        """
        ...

    @abstractmethod
    async def download(
        self,
        session: aiohttp.ClientSession,
        paper: dict,
        output_dir: Path
    ) -> Optional[Path]:
        """
        Download the PDF for a single paper.

        Args:
            session:   An aiohttp ClientSession to reuse connections.
            paper:     Paper metadata dict (with at least 'pdf_url' or source-specific fields).
            output_dir: Directory where the PDF will be saved.

        Returns:
            Path to the downloaded file, or None if the download failed.
        """
        ...