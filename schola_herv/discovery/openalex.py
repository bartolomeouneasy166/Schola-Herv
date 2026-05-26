"""
OpenAlex paper discovery module.
Uses the free OpenAlex API (no key required, but polite email recommended).
"""

import asyncio
import logging
import time
from typing import List, Optional

import aiohttp

from .base import BaseSearcher

logger = logging.getLogger("schola_herv.discovery.openalex")

OPENALEX_WORKS = "https://api.openalex.org/works"


def _reconstruct_abstract(inverted_index: dict) -> str:
    """Reconstruct abstract text from OpenAlex abstract_inverted_index."""
    if not inverted_index:
        return ""
    try:
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        return " ".join(w for _, w in sorted(word_positions))
    except Exception:
        return ""


class OpenAlexSearcher(BaseSearcher):
    """Search OpenAlex for papers matching keywords."""

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
        # Combine topics and keywords
        all_terms = topics + (keywords or [])
        if not all_terms:
            return []
        query = " ".join(all_terms)

        papers = []
        per_page = min(200, max_results)
        page = 1
        self._last_request = 0

        # Build year filter using correct OpenAlex range syntax
        year_filter = None
        if year_start and year_end:
            year_filter = f"publication_year:{year_start}-{year_end}"
        elif year_start:
            year_filter = f"publication_year:{year_start}-"
        elif year_end:
            year_filter = f"publication_year:-{year_end}"

        async with aiohttp.ClientSession(
            headers={"User-Agent": f"Schola-Herv/1.0 (mailto:{self.email})"}
        ) as session:
            while len(papers) < max_results:
                # Rate limit
                await self._rate_limit()

                params = {
                    "search": query,
                    "per_page": per_page,
                    "page": page,
                }
                if year_filter:
                    params["filter"] = year_filter

                try:
                    async with session.get(OPENALEX_WORKS, params=params, timeout=30) as resp:
                        if resp.status == 429:
                            logger.warning("OpenAlex rate limited (429); sleeping 5s")
                            await asyncio.sleep(5)
                            continue
                        if resp.status != 200:
                            logger.error("OpenAlex returned status %d; stopping", resp.status)
                            break
                        data = await resp.json()
                        results_raw = data.get("results", [])
                        if not results_raw:
                            break

                        for item in results_raw:
                            paper = self._parse_item(item)
                            if paper:
                                papers.append(paper)
                                if len(papers) >= max_results:
                                    break
                        page += 1
                        if page > 50:  # safety break
                            break
                except aiohttp.ClientError as exc:
                    logger.warning("OpenAlex network error: %s; retrying in 2s", exc)
                    await asyncio.sleep(2)
                    continue
                except Exception as exc:
                    logger.error("Unexpected error during OpenAlex search: %s", exc)
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
        try:
            title = item.get("title", "No title")
            authors_list = []
            for authorship in item.get("authorships", []):
                author = authorship.get("author", {})
                name = author.get("display_name", "")
                if name:
                    authors_list.append(name)
            year = item.get("publication_year")

            # Strip both https://doi.org/ and http://doi.org/ prefixes
            raw_doi = item.get("doi", "") or ""
            doi = raw_doi.replace("https://doi.org/", "").replace("http://doi.org/", "")

            # OpenAlex provides `best_oa_url` if an OA PDF exists
            pdf_url = item.get("best_oa_url")

            # Reconstruct abstract from inverted index
            abstract = _reconstruct_abstract(item.get("abstract_inverted_index") or {})

            journal = None
            loc = item.get("primary_location", {}) or {}
            source = loc.get("source", {}) or {}
            journal = source.get("display_name")
            return {
                "title": title,
                "authors": authors_list if authors_list else ["Unknown"],
                "year": year,
                "doi": doi if doi else None,
                "pdf_url": pdf_url,
                "source": "openalex",
                "abstract": abstract if abstract else None,
                "journal": journal,
            }
        except Exception as exc:
            logger.warning("Failed to parse OpenAlex item: %s", exc)
            return None
