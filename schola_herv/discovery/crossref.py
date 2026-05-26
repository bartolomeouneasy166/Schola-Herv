"""
Crossref paper discovery module.
"""

import asyncio
import logging
from typing import List, Optional

from habanero import Crossref
from .base import BaseSearcher

logger = logging.getLogger("schola_herv.discovery.crossref")


class CrossrefSearcher(BaseSearcher):
    """Search Crossref for papers by topic/keyword using the public API."""

    def __init__(self):
        self.cr = Crossref()

    async def search(
        self,
        topics: List[str],
        keywords: Optional[List[str]] = None,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        max_results: int = 100,
    ) -> List[dict]:
        def _sync_search() -> List[dict]:
            # Combine topics and keywords into a single query string
            query = " ".join(topics)
            if keywords:
                query += " " + " ".join(keywords)

            # Build server-side date filter for habanero
            date_filter: dict = {}
            if year_start:
                date_filter["from-pub-date"] = str(year_start)
            if year_end:
                date_filter["until-pub-date"] = str(year_end)

            results = []
            try:
                kwargs = dict(
                    query=query,
                    limit=min(max_results, 1000),
                    sort="relevance",
                )
                if date_filter:
                    kwargs["filter"] = date_filter

                response = self.cr.works(**kwargs)
                items = response.get("message", {}).get("items", [])
            except Exception as exc:
                logger.error("Crossref API call failed: %s", exc)
                return []

            for item in items:
                # Extract year
                year = None
                try:
                    date_parts = item.get("published-print", {}).get("date-parts", [[None]])
                    if date_parts and date_parts[0]:
                        year = date_parts[0][0]
                    # If still no year, try created date
                    if not year:
                        created_parts = item.get("created", {}).get("date-parts", [[None]])
                        if created_parts and created_parts[0]:
                            year = created_parts[0][0]
                    year = int(year) if year else None
                except (ValueError, TypeError) as exc:
                    logger.warning("Could not parse year for Crossref item: %s", exc)
                    year = None

                if not self._matches_year(year, year_start, year_end):
                    continue

                # Title – Crossref returns a list
                title = (item.get("title") or ["No title"])[0]

                # Authors
                authors = []
                try:
                    for author in item.get("author", []):
                        given = author.get("given", "")
                        family = author.get("family", "")
                        name = f"{given} {family}".strip()
                        if name:
                            authors.append(name)
                except Exception as exc:
                    logger.warning("Failed to parse authors for '%s': %s", title, exc)

                results.append(
                    {
                        "title": title,
                        "authors": authors or ["Unknown"],
                        "year": year,
                        "doi": item.get("DOI"),
                        "pdf_url": None,  # will be resolved later via Unpaywall
                        "source": "crossref",
                        "abstract": item.get("abstract"),
                    }
                )
                if len(results) >= max_results:
                    break

            return results

        return await asyncio.to_thread(_sync_search)
