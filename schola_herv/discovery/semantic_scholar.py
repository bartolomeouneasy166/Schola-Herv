"""
Semantic Scholar paper discovery module.
Provides keyword-based search and citation-based search (--cites).
"""

import asyncio
import logging
import urllib.parse
from typing import List, Optional

import aiohttp

from .base import BaseSearcher

logger = logging.getLogger("schola_herv.discovery.semantic_scholar")

S2_PAPER = "https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
S2_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_BATCH_FIELDS = "citationCount,externalIds,year,title,authors"
S2_CITATION_FIELDS = (
    "title,year,authors,externalIds,publicationVenue,abstract,openAccessPdf,citationCount"
)


class SemanticScholarSearcher(BaseSearcher):
    """Search Semantic Scholar for papers by keyword or citation."""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self._last_request = 0

    # ------------------------------------------------------------------
    # Keyword-based search
    # ------------------------------------------------------------------
    async def search(
        self,
        topics: List[str],
        keywords: Optional[List[str]] = None,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        max_results: int = 100,
    ) -> List[dict]:
        """Keyword-based paper search via the S2 /paper/search endpoint."""
        all_terms = topics + (keywords or [])
        if not all_terms:
            return []
        query = " ".join(all_terms)

        papers: List[dict] = []
        offset = 0
        limit = min(100, max_results)

        async with aiohttp.ClientSession(
            headers={"User-Agent": "Schola-Herv/1.0 (mailto:researcher@example.com)"}
        ) as session:
            while len(papers) < max_results:
                await self._rate_limit()
                params = {
                    "query": query,
                    "limit": limit,
                    "offset": offset,
                    "fields": "title,authors,year,externalIds,citationCount,openAccessPdf",
                }
                try:
                    async with session.get(S2_SEARCH, params=params, timeout=30) as resp:
                        if resp.status == 429:
                            logger.warning("S2 search rate limited (429); sleeping 5s")
                            await asyncio.sleep(5)
                            continue
                        if resp.status != 200:
                            logger.error("S2 search returned status %d; stopping", resp.status)
                            break
                        data = await resp.json()
                        items = data.get("data", [])
                        if not items:
                            break

                        for item in items:
                            # Apply year filter client-side
                            year = item.get("year")
                            if not self._matches_year(year, year_start, year_end):
                                continue
                            paper = self._parse_item(item)
                            if paper:
                                papers.append(paper)
                                if len(papers) >= max_results:
                                    break

                        if len(items) < limit:
                            break
                        offset += len(items)

                except aiohttp.ClientError as exc:
                    logger.warning("S2 search network error: %s; retrying in 2s", exc)
                    await asyncio.sleep(2)
                    continue
                except Exception as exc:
                    logger.error("Unexpected error during S2 search: %s", exc)
                    await asyncio.sleep(2)
                    continue

        return papers[:max_results]

    # ------------------------------------------------------------------
    # Citation-based search
    # ------------------------------------------------------------------
    async def search_citing(
        self,
        paper_id: str,          # Semantic Scholar Corpus ID or DOI
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        max_results: int = 500,
    ) -> List[dict]:
        """Fetch papers that cite the given paper (by ID or DOI)."""
        s2_id = paper_id
        if paper_id.startswith("10."):          # It's a DOI
            s2_id = await self._resolve_doi(paper_id)

        if not s2_id:
            logger.warning("Could not resolve paper identifier: %s", paper_id)
            return []

        papers: List[dict] = []
        offset = 0
        limit = min(500, max_results)

        async with aiohttp.ClientSession(
            headers={"User-Agent": "Schola-Herv/1.0 (mailto:researcher@example.com)"}
        ) as session:
            while len(papers) < max_results:
                await self._rate_limit()
                url = S2_PAPER.format(paper_id=s2_id)
                params = {
                    "offset": offset,
                    "limit": limit,
                    "fields": S2_CITATION_FIELDS,
                }
                # Apply year filter server-side where S2 supports it
                if year_start and year_end:
                    params["year"] = f"{year_start}-{year_end}"
                elif year_start:
                    params["year"] = f"{year_start}-"
                elif year_end:
                    params["year"] = f"-{year_end}"

                try:
                    async with session.get(url, params=params, timeout=30) as resp:
                        if resp.status == 429:
                            logger.warning("S2 citations rate limited (429); sleeping 5s")
                            await asyncio.sleep(5)
                            continue
                        if resp.status != 200:
                            logger.error(
                                "S2 citations returned status %d for %s; stopping",
                                resp.status, paper_id,
                            )
                            break
                        data = await resp.json()
                        items = data.get("data", [])
                        if not items:
                            break
                        for item in items:
                            citing = item.get("citingPaper") or item
                            if not citing:
                                continue
                            paper = self._parse_item(citing)
                            if paper:
                                papers.append(paper)
                                if len(papers) >= max_results:
                                    break
                        if len(items) < limit:
                            break
                        offset += len(items)
                except aiohttp.ClientError as exc:
                    logger.warning("S2 citations network error: %s; retrying in 2s", exc)
                    await asyncio.sleep(2)
                    continue
                except Exception as exc:
                    logger.error("Unexpected error during S2 citations fetch: %s", exc)
                    await asyncio.sleep(2)
                    continue

        return papers

    # ------------------------------------------------------------------
    # DOI resolution with fallback
    # ------------------------------------------------------------------
    async def _resolve_doi(self, doi: str) -> Optional[str]:
        """Convert a DOI to a Semantic Scholar Corpus ID, with retries."""
        encoded_doi = urllib.parse.quote(doi, safe="")
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{encoded_doi}"
            f"?fields=paperId,{S2_BATCH_FIELDS}"
        )

        max_retries = 3
        base_delay = 5  # seconds

        for attempt in range(max_retries):
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            paper_id = data.get("paperId")
                            return paper_id if paper_id else None
                        elif resp.status == 429:
                            wait = base_delay * (2 ** attempt)
                            logger.warning(
                                "S2 DOI lookup rate limited (429); waiting %ds (attempt %d/%d)",
                                wait, attempt + 1, max_retries,
                            )
                            await asyncio.sleep(wait)
                            continue
                        elif resp.status == 404:
                            return None   # not found – stop retries
                        else:
                            logger.warning(
                                "S2 DOI lookup returned %d for %s", resp.status, doi
                            )
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2)
                                continue
                except aiohttp.ClientError as exc:
                    logger.warning(
                        "S2 DOI lookup network error (attempt %d/%d): %s",
                        attempt + 1, max_retries, exc,
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                except Exception as exc:
                    logger.error("Unexpected error in S2 DOI lookup: %s", exc)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue

        # If direct lookup exhausted, try fallback via title
        return await self._resolve_via_title(doi)

    async def _resolve_via_title(self, doi: str) -> Optional[str]:
        """Fallback: get title from Crossref and search S2."""
        title = await self._get_title_from_crossref(doi)
        if not title:
            return None
        encoded_title = urllib.parse.quote(title)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    S2_SEARCH,
                    params={
                        "query": encoded_title,
                        "limit": 1,
                        "fields": f"paperId,{S2_BATCH_FIELDS}",
                    },
                    timeout=10,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("data", [])
                        if items:
                            return items[0].get("paperId")
                    elif resp.status == 429:
                        logger.warning("S2 title-search also rate limited; giving up.")
                    else:
                        logger.warning("S2 title-search returned status %d", resp.status)
            except aiohttp.ClientError as exc:
                logger.warning("S2 title-search network error: %s", exc)
            except Exception as exc:
                logger.error("Unexpected error in S2 title-search: %s", exc)
        return None

    async def _get_title_from_crossref(self, doi: str) -> Optional[str]:
        """Retrieve the article title from Crossref API."""
        url = f"https://api.crossref.org/works/{doi}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        title = (data.get("message", {}).get("title") or [""])[0]
                        return title or None
                    else:
                        logger.warning("Crossref title lookup returned status %d for %s", resp.status, doi)
            except aiohttp.ClientError as exc:
                logger.warning("Crossref title lookup network error for %s: %s", doi, exc)
            except Exception as exc:
                logger.error("Unexpected error in Crossref title lookup: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _rate_limit(self):
        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_request
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)
        self._last_request = asyncio.get_running_loop().time()

    def _parse_item(self, item: dict) -> Optional[dict]:
        try:
            title = item.get("title", "No title")
            authors = [a.get("name", "") for a in item.get("authors", [])]
            year = item.get("year")
            external = item.get("externalIds", {}) or {}
            doi = external.get("DOI")
            pdf_info = item.get("openAccessPdf") or {}
            pdf_url = pdf_info.get("url")
            journal_obj = item.get("publicationVenue") or {}
            journal = journal_obj.get("name")
            abstract = item.get("abstract")
            citation_count = item.get("citationCount")
            return {
                "title": title,
                "authors": authors if authors else ["Unknown"],
                "year": year,
                "doi": doi,
                "pdf_url": pdf_url,
                "source": "semantic_scholar",
                "abstract": abstract,
                "journal": journal,
                "citation_count": citation_count,
            }
        except Exception as exc:
            logger.warning("Failed to parse S2 item: %s", exc)
            return None
