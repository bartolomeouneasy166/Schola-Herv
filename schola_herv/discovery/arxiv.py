"""
ArXiv paper discovery module using direct API calls.
No dependency on the 'arxiv' library.
"""

import asyncio
import logging
import re
from typing import List, Optional

import aiohttp
from .base import BaseSearcher

logger = logging.getLogger("schola_herv.discovery.arxiv")

ARXIV_API = "http://export.arxiv.org/api/query"
MAX_429_RETRIES = 5


class ArxivSearcher(BaseSearcher):
    USER_AGENT = "Schola-Herv/1.0 (mailto:researcher@example.com)"

    def __init__(self, delay_seconds: float = 3.0, max_retries: int = 3):
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self._last_request = 0

    async def search(
        self,
        topics: List[str],
        keywords: Optional[List[str]] = None,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        max_results: int = 100,
    ) -> List[dict]:
        all_terms = [f'all:"{t}"' for t in topics]
        if keywords:
            all_terms.extend(f'all:"{kw}"' for kw in keywords)
        query = " AND ".join(all_terms)
        papers = []
        start = 0
        batch_size = 100
        retry_429_count = 0

        async with aiohttp.ClientSession(
            headers={"User-Agent": self.USER_AGENT}
        ) as session:
            while len(papers) < max_results:
                await self._rate_limit()
                params = {
                    "search_query": query,
                    "start": start,
                    "max_results": min(batch_size, max_results - len(papers)),
                    "sortBy": "relevance",
                    "sortOrder": "descending",
                }
                try:
                    async with session.get(ARXIV_API, params=params, timeout=30) as resp:
                        if resp.status == 429:
                            retry_429_count += 1
                            if retry_429_count > MAX_429_RETRIES:
                                logger.error(
                                    "ArXiv rate limit exceeded max retries (%d); giving up.",
                                    MAX_429_RETRIES,
                                )
                                break
                            wait = 10 * retry_429_count
                            logger.warning(
                                "ArXiv rate limited (429); sleeping %ds (retry %d/%d)",
                                wait, retry_429_count, MAX_429_RETRIES,
                            )
                            await asyncio.sleep(wait)
                            continue
                        # Successful response resets the 429 counter
                        retry_429_count = 0
                        if resp.status != 200:
                            logger.error("ArXiv returned status %d; stopping", resp.status)
                            break
                        xml = await resp.text()
                        batch = self._parse_xml(xml, year_start, year_end)
                        if not batch:
                            break
                        papers.extend(batch)
                        start += len(batch)
                        if len(batch) < params["max_results"]:
                            break
                except aiohttp.ClientError as exc:
                    logger.warning("ArXiv network error: %s; retrying in 5s", exc)
                    await asyncio.sleep(5)
                    continue
                except Exception as exc:
                    logger.error("Unexpected error during ArXiv search: %s", exc)
                    await asyncio.sleep(5)
                    continue

        return papers[:max_results]

    async def _rate_limit(self):
        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_request
        if elapsed < self.delay_seconds:
            await asyncio.sleep(self.delay_seconds - elapsed)
        self._last_request = asyncio.get_running_loop().time()

    def _parse_xml(self, xml: str, year_start: Optional[int], year_end: Optional[int]) -> List[dict]:
        papers = []
        entries = xml.split("<entry>")[1:]
        for entry in entries:
            try:
                title = self._tag(entry, "title")
                authors = re.findall(r"<name>(.*?)</name>", entry)
                year_str = self._tag(entry, "published")[:4]
                year = int(year_str) if year_str.isdigit() else None
                if year and (
                    (year_start and year < year_start) or (year_end and year > year_end)
                ):
                    continue
                doi = self._tag(entry, "arxiv:doi")
                pdf_url = None
                for part in entry.split("<link "):
                    if 'title="pdf"' in part or "title='pdf'" in part:
                        m = re.search(r"""href=["']([^"']+)["']""", part)
                        if m:
                            pdf_url = m.group(1)
                            break
                arxiv_id = self._tag(entry, "id").split("/abs/")[-1]
                abstract = self._tag(entry, "summary").strip()
                papers.append(
                    {
                        "title": title.strip(),
                        "authors": authors if authors else ["Unknown"],
                        "year": year,
                        "doi": doi if doi else None,
                        "pdf_url": pdf_url,
                        "source": "arxiv",
                        "id": arxiv_id,
                        "abstract": abstract,
                    }
                )
            except Exception as exc:
                logger.warning("Failed to parse ArXiv entry: %s", exc)
                continue
        return papers

    @staticmethod
    def _tag(xml: str, tag: str) -> str:
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.DOTALL)
        return re.sub(r"<[^>]+>", "", m.group(1)) if m else ""
