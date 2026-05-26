"""
Citation-based quality filtering using Semantic Scholar API.
Free, no API key required.
"""

import asyncio
import logging
import aiohttp
from typing import List, Dict, Optional

logger = logging.getLogger("schola_herv.quality.semantic_scholar")

S2_API = "https://api.semanticscholar.org/graph/v1/paper"
S2_BATCH = "https://api.semanticscholar.org/graph/v1/paper/batch"
FIELDS = "citationCount,externalIds,year,title"


async def get_citation_counts(papers: List[dict]) -> List[dict]:
    """
    Enrich each paper with citationCount from Semantic Scholar.
    Uses batch DOI lookup where possible; falls back to title search.
    """
    # Build DOI list for batch POST
    dois = [p.get("doi") for p in papers if p.get("doi")]
    citation_map: Dict[str, int] = {}

    async with aiohttp.ClientSession() as session:
        # Batch lookup by DOI (POST)
        if dois:
            payload = {"ids": [f"DOI:{doi}" for doi in dois]}
            try:
                async with session.post(
                    S2_BATCH,
                    json=payload,
                    params={"fields": FIELDS},
                    timeout=30,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data:
                            if item is not None:
                                external_ids = item.get("externalIds", {}) or {}
                                doi_found = external_ids.get("DOI")
                                if doi_found:
                                    citation_map[doi_found.lower()] = item.get(
                                        "citationCount", 0
                                    )
                    elif resp.status == 429:
                        logger.warning("S2 batch lookup rate limited (429); skipping batch.")
                    else:
                        logger.warning(
                            "S2 batch lookup returned status %d; skipping batch.", resp.status
                        )
            except aiohttp.ClientError as exc:
                logger.warning("S2 batch lookup network error: %s", exc)
            except Exception as exc:
                logger.error("Unexpected error in S2 batch lookup: %s", exc)

        # For papers without DOI or missed in batch, try title search (one by one – slow)
        for paper in papers:
            if paper.get("doi") and paper["doi"].lower() in citation_map:
                paper["citation_count"] = citation_map[paper["doi"].lower()]
                continue

            # Fallback: search by title
            title = paper.get("title", "")
            if title:
                try:
                    async with session.get(
                        f"{S2_API}/search",
                        params={
                            "query": title,
                            "limit": 1,
                            "fields": FIELDS,
                        },
                        timeout=10,
                    ) as resp:
                        if resp.status == 200:
                            search_data = await resp.json()
                            if search_data.get("data"):
                                top = search_data["data"][0]
                                paper["citation_count"] = top.get("citationCount", 0)
                                continue
                        elif resp.status == 429:
                            logger.warning(
                                "S2 title search rate limited (429) for '%s'; defaulting to 0.",
                                title,
                            )
                        else:
                            logger.warning(
                                "S2 title search returned status %d for '%s'",
                                resp.status, title,
                            )
                except aiohttp.ClientError as exc:
                    logger.warning(
                        "S2 title search network error for '%s': %s", title, exc
                    )
                except Exception as exc:
                    logger.error(
                        "Unexpected error in S2 title search for '%s': %s", title, exc
                    )

            paper["citation_count"] = 0   # default

    return papers


def filter_by_citations(
    papers: List[dict],
    min_citations: Optional[int] = None,
    max_dwn_cites: Optional[int] = None,
) -> List[dict]:
    """
    Filter/sort papers by citation count.
    - min_citations: keep only papers with >= N citations.
    - max_dwn_cites: keep only the top N most-cited papers (after optional min_citations filter).
    If neither given, returns unsorted original list.
    """
    if min_citations is not None:
        papers = [p for p in papers if p.get("citation_count", 0) >= min_citations]

    if max_dwn_cites is not None and max_dwn_cites > 0:
        # Sort by citation count descending, then take top N
        papers = sorted(papers, key=lambda p: p.get("citation_count", 0), reverse=True)
        papers = papers[:max_dwn_cites]

    return papers
