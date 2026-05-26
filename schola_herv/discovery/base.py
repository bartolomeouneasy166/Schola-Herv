"""
Abstract base class for all paper discovery modules.
"""

from abc import ABC, abstractmethod
from typing import List, Optional


class BaseSearcher(ABC):
    """Interface that every discovery module must implement."""

    @abstractmethod
    async def search(
        self,
        topics: List[str],
        keywords: Optional[List[str]] = None,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        max_results: int = 100
    ) -> List[dict]:
        """
        Search for papers matching the given criteria.

        Args:
            topics:       List of main research topics (e.g. ["machine learning", "NLP"]).
            keywords:     Additional keywords to refine the search.
            year_start:   Earliest publication year to include (inclusive).
            year_end:     Latest publication year to include (inclusive).
            max_results:  Maximum number of results to return.

        Returns:
            List of paper metadata dicts, each with:
                - title (str)
                - authors (list of str)
                - year (int)
                - doi (str or None)
                - pdf_url (str or None)
                - source (str)       # e.g. "arxiv", "pubmed"
                - abstract (str or None)  # optional
        """
        ...

    @staticmethod
    def _matches_year(year: Optional[int], year_start: Optional[int], year_end: Optional[int]) -> bool:
        """Helper: check if a year falls within the requested range."""
        if year is None:
            return True  # if year is unknown, include anyway
        if year_start is not None and year < year_start:
            return False
        if year_end is not None and year > year_end:
            return False
        return True