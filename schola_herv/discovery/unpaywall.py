"""
Unpaywall enricher – adds open-access PDF URLs to paper metadata using the Unpaywall API.
"""

import asyncio
import logging
import aiohttp
from typing import List, Optional

logger = logging.getLogger("schola_herv.discovery.unpaywall")

UNPAYWALL_API = "https://api.unpaywall.org/v2/{doi}?email={email}"


class UnpaywallEnricher:
    """Resolves DOIs to open-access PDF links via Unpaywall."""

    def __init__(self, email: str = "researcher@example.com", rate_limit: float = 1.0):
        self.email = email
        self.rate_limit = rate_limit
        # NOTE: Do NOT create asyncio.Semaphore here — it must be created inside
        # an async context to avoid binding to the wrong event loop.

    async def enrich(self, papers: List[dict]) -> List[dict]:
        """
        For every paper that has a DOI, try to find a free PDF link.
        Papers without a DOI are returned unchanged.

        Runs up to 5 requests concurrently using a semaphore created inside
        this coroutine (correct event-loop scope).
        """
        semaphore = asyncio.Semaphore(5)

        async with aiohttp.ClientSession() as session:
            tasks = [
                self._fetch_and_enrich(session, semaphore, paper)
                for paper in papers
            ]
            enriched = await asyncio.gather(*tasks)

        return list(enriched)

    async def _fetch_and_enrich(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        paper: dict,
    ) -> dict:
        """Enrich a single paper dict in-place; always returns the paper."""
        doi = paper.get("doi")
        if not doi:
            return paper

        pdf_url = await self._fetch_pdf(session, semaphore, doi)
        if pdf_url:
            paper["pdf_url"] = pdf_url
        return paper

    async def _fetch_pdf(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        doi: str,
    ) -> Optional[str]:
        """Call Unpaywall for a single DOI and return the best PDF link, if any."""
        url = UNPAYWALL_API.format(doi=doi, email=self.email)

        async with semaphore:
            await asyncio.sleep(self.rate_limit)  # polite delay inside the semaphore
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        best_oa = data.get("best_oa_location")
                        if best_oa and best_oa.get("url_for_pdf"):
                            return best_oa["url_for_pdf"]
                    elif resp.status == 404:
                        logger.warning("Unpaywall: DOI not found: %s", doi)
                    elif resp.status == 429:
                        logger.warning("Unpaywall: rate limited for DOI: %s", doi)
                    else:
                        logger.warning(
                            "Unpaywall: unexpected status %d for DOI: %s", resp.status, doi
                        )
            except aiohttp.ClientError as exc:
                logger.warning("Unpaywall network error for DOI %s: %s", doi, exc)
            except Exception as exc:
                logger.error("Unpaywall unexpected error for DOI %s: %s", doi, exc)
        return None
