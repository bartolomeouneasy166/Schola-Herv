"""
PubMed paper discovery module using NCBI Entrez.
"""

import asyncio
import os
from typing import List, Optional

from Bio import Entrez
from .base import BaseSearcher


class PubMedSearcher(BaseSearcher):
    """Search PubMed for papers matching topic/keyword queries."""

    def __init__(self, email: str = None):
        # Always set Entrez.email before making requests
        self.email = email or os.environ.get(
            "ENTREZ_EMAIL", "your.email@example.com"
        )

    async def search(
        self,
        topics: List[str],
        keywords: Optional[List[str]] = None,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        max_results: int = 100,
    ) -> List[dict]:
        """Perform a PubMed search and return metadata."""

        def _sync_search() -> List[dict]:
            Entrez.email = self.email

            # Build query: topics and keywords as all-field terms
            query_parts = [f'"{t}"[All Fields]' for t in topics]
            if keywords:
                query_parts += [f'"{kw}"[All Fields]' for kw in keywords]
            query = " AND ".join(query_parts)

            # Add date range if provided
            if year_start or year_end:
                if year_start and year_end:
                    query += f' AND ("{year_start}"[Date - Publication] : "{year_end}"[Date - Publication])'
                elif year_start:
                    query += f' AND ("{year_start}"[Date - Publication] : "3000"[Date - Publication])'
                elif year_end:
                    query += f' AND ("1800"[Date - Publication] : "{year_end}"[Date - Publication])'

            # 1. Get IDs
            handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
            record = Entrez.read(handle)
            handle.close()
            id_list = record.get("IdList", [])

            if not id_list:
                return []

            # 2. Fetch details
            handle = Entrez.efetch(db="pubmed", id=id_list, rettype="xml")
            articles = Entrez.read(handle)
            handle.close()

            papers = []
            for article in articles.get("PubmedArticle", []):
                paper = self._parse_article(article)
                if paper:
                    papers.append(paper)
                    if len(papers) >= max_results:
                        break
            return papers

        return await asyncio.to_thread(_sync_search)

    def _parse_article(self, article) -> Optional[dict]:
        """Parse a single PubMed article into standard metadata dict."""
        try:
            medline = article["MedlineCitation"]["Article"]
            title = medline.get("ArticleTitle", "No title")

            # Authors
            authors = []
            author_list = medline.get("AuthorList", [])
            for author in author_list:
                last = author.get("LastName", "")
                fore = author.get("ForeName", "")
                if last:
                    authors.append(f"{last}, {fore}".strip(", "))
                elif fore:
                    authors.append(fore)

            # Year
            try:
                year = int(
                    medline["Journal"]["JournalIssue"]["PubDate"].get("Year", 0)
                )
            except (KeyError, ValueError):
                year = 0

            # DOI
            doi = None
            for eid in medline.get("ELocationID", []):
                if eid.attributes.get("EIdType") == "doi":
                    doi = str(eid)
            article_id_list = article["PubmedData"]["ArticleIdList"]
            for aid in article_id_list:
                if aid.attributes.get("IdType") == "doi":
                    doi = str(aid)

            # Abstract
            abstract = None
            if medline.get("Abstract"):
                abstract = " ".join(medline["Abstract"]["AbstractText"])

            return {
                "title": title,
                "authors": authors,
                "year": year,
                "doi": doi,
                "pdf_url": None,          # PubMed doesn't offer direct PDF links
                "source": "pubmed",
                "abstract": abstract,
                "pubmed_id": article["MedlineCitation"]["PMID"],
            }
        except Exception:
            return None