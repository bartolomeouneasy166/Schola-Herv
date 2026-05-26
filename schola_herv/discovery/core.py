"""
CORE (core.ac.uk) paper discovery module.
CORE aggregates open-access full texts from repositories worldwide.
No API key required for basic use.
"""

import asyncio
import time
from typing import List, Optional

import aiohttp

from .base import BaseSearcher
from schola_herv.utils.logger import setup_logger

logger = setup_logger(__name__)

CORE_API = "https://api.core.ac.uk/v3/search/works"


class CoreSearcher(BaseSearcher):
    """Search CORE for open-access papers."""

    def __init__(self, email: str = "researcher@example.com", delay: float = 1.0):
        self.email = email
        self.delay = delay
        self._last_request = 0

    async def search(
        self,
        topics: List[str],
        keywords: Optional[List[str]] = None,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        max_results: int = 100,
    ) -> List[dict]:
        """Search CORE by keywords and return paper metadata."""
        # Combine topics and keywords with OR for better recall
        all_terms = topics + (keywords or [])
        if not all_terms:
            return []
        query = " OR ".join(f'"{term}"' for term in all_terms)

        papers = []
        offset = 0
        page_size = min(100, max_results)
        max_pages = 20  # safety limit

        async with aiohttp.ClientSession(
            headers={"User-Agent": f"Schola-Herv/1.0 (mailto:{self.email})"}
        ) as session:
            for _ in range(max_pages):
                if len(papers) >= max_results:
                    break

                await self._rate_limit()

                params = {
                    "q": query,
                    "offset": offset,
                    "limit": page_size,
                    "scroll": False,
                    "sort": "relevance",
                }
                if year_start:
                    params["yearMin"] = year_start
                if year_end:
                    params["yearMax"] = year_end

                try:
                    async with session.get(CORE_API, params=params, timeout=30) as resp:
                        if resp.status == 429:
                            await asyncio.sleep(5)
                            continue
                        if resp.status != 200:
                            break
                        data = await resp.json()
                        items = data.get("results", [])
                        if not items:
                            break

                        for item in items:
                            paper = self._parse_item(item)
                            if paper:
                                papers.append(paper)
                                if len(papers) >= max_results:
                                    break
                        offset += len(items)
                        if len(items) < page_size:
                            break
                except Exception:
                    await asyncio.sleep(2)
                    continue
        return papers[:max_results]

    async def _rate_limit(self):
        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_request
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)
        self._last_request = asyncio.get_running_loop().time()

    def _parse_item(self, item: dict) -> Optional[dict]:
        """Convert CORE JSON to standard paper dict."""
        try:
            title = item.get("title", "No title")
            authors = [
                a.get("name", "") for a in item.get("authors", []) if a.get("name")
            ]
            year = item.get("yearPublished")
            doi = item.get("doi")
            # CORE provides download URL directly
            pdf_url = item.get("downloadUrl") or (
                item.get("links", [{}])[0].get("url") if item.get("links") else None
            )
            abstract = item.get("abstract")
            journal = item.get("publisher")  # CORE uses publisher as journal-like field
            return {
                "title": title,
                "authors": authors if authors else ["Unknown"],
                "year": year,
                "doi": doi,
                "pdf_url": pdf_url,
                "source": "core",
                "abstract": abstract,
                "journal": journal,
            }
        except Exception:
            return None