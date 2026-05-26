"""
Schola-Herv harvester – complete with AI relevance, query expansion, summarisation,
and survey support (return_papers / no_download).
"""

import asyncio
import csv
import io
import re
import socket
import time
from pathlib import Path
from typing import List, Optional

import aiohttp

from schola_herv.downloader.manager import DownloadManager
from schola_herv.utils.logger import setup_logger
from schola_herv.utils.pdf_utils import generate_filename
from schola_herv.discovery.openalex import OpenAlexSearcher
from schola_herv.discovery.semantic_scholar import SemanticScholarSearcher
from schola_herv.discovery.core import CoreSearcher
from schola_herv.config import load_config
from schola_herv.ai.ollama_manager import ensure_ollama_running

logger = setup_logger(__name__)

CROSSREF_API = "https://api.crossref.org/works"
UNPAYWALL_API = "https://api.unpaywall.org/v2/{doi}?email={email}"
ARXIV_API = "https://export.arxiv.org/api/query"
S2_BATCH = "https://api.semanticscholar.org/graph/v1/paper/batch"


# ----------------------------------------------------------------------
# Helpers for DOI extraction
# ----------------------------------------------------------------------
def _extract_dois(text: str) -> List[str]:
    doi_pattern = r'\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b'
    return [doi.strip() for doi in re.findall(doi_pattern, text, re.IGNORECASE)]


def _read_doi_file(filepath: str) -> List[str]:
    p = Path(filepath)
    if not p.exists():
        logger.error(f"DOI file not found: {filepath}")
        return []
    with open(p, 'r', encoding='utf-8') as f:
        content = f.read()
    return _extract_dois(content)


# ----------------------------------------------------------------------
# Filter helpers
# ----------------------------------------------------------------------
def _apply_skip_words(papers: List[dict], skip_words: List[str]) -> List[dict]:
    filtered = []
    for paper in papers:
        title = (paper.get("title") or "").lower()
        abstract = (paper.get("abstract") or "").lower()
        combined = title + " " + abstract
        if any(word.lower() in combined for word in skip_words):
            continue
        filtered.append(paper)
    return filtered


def _apply_year_filter(papers: List[dict], max_dwn_year: Optional[int]) -> List[dict]:
    if max_dwn_year is None or max_dwn_year <= 0:
        return papers
    sorted_papers = sorted(papers, key=lambda p: p.get("year") or 0, reverse=True)
    return sorted_papers[:max_dwn_year]


# ----------------------------------------------------------------------
# Reporting helpers
# ----------------------------------------------------------------------
def _write_markdown_report(output_dir: Path, papers: List[dict], stats: dict) -> None:
    report_path = output_dir / "report.md"
    lines = [
        "# Schola-Herv Harvest Report",
        "",
        f"- **Papers discovered:** {stats['found']}",
        f"- **Papers downloaded:** {stats['downloaded']}",
        f"- **Output directory:** {stats['output']}",
        "",
        "## Downloaded Papers",
        "",
    ]
    if not papers:
        lines.append("No papers downloaded.")
    else:
        lines.append("| # | Title | Year | Citations | Journal | Summary |")
        lines.append("|---|-------|------|-----------|---------|---------|")
        for i, paper in enumerate(papers, 1):
            title = (paper.get("title") or "Untitled")[:100]
            year = paper.get("year") or "—"
            cites = paper.get("citation_count", 0)
            journal = (paper.get("journal") or "—")[:80]
            summary = (paper.get("ai_summary") or "—")[:150]
            lines.append(f"| {i} | {title} | {year} | {cites} | {journal} | {summary} |")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"Markdown report saved to {report_path}")


def _write_csv_report(output_dir: Path, papers: List[dict]) -> None:
    csv_path = output_dir / "metadata.csv"
    with open(csv_path, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["DOI", "Title", "Authors", "Year", "Citations", "Journal", "AI Summary", "PDF Filename"])
        for paper in papers:
            doi = paper.get("doi") or ""
            title = paper.get("title") or ""
            authors = "; ".join(paper.get("authors", []))
            year = paper.get("year") or ""
            cites = paper.get("citation_count", 0)
            journal = paper.get("journal") or ""
            filename = generate_filename(paper)
            ai_summary = paper.get("ai_summary", "")
            writer.writerow([doi, title, authors, year, cites, journal, ai_summary, filename])
    logger.info(f"CSV metadata saved to {csv_path}")


def _author_to_bibtex(author: str) -> str:
    author = author.strip()
    if "," in author:
        return author
    parts = author.split()
    if len(parts) >= 2:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    return author


def _write_bibtex(output_dir: Path, papers: List[dict]) -> None:
    bib_path = output_dir / "export.bib"
    entries = []
    for paper in papers:
        doi = paper.get("doi") or "unknown"
        title = paper.get("title") or "No Title"
        year = paper.get("year") or ""
        journal = paper.get("journal")
        entry_type = "article" if journal else "misc"
        authors = paper.get("authors", [])
        author_field = " and ".join(_author_to_bibtex(a) for a in authors) if authors else "{}"
        key = doi.replace("/", "_").replace(":", "_") if doi else "ref_" + re.sub(r'\W+', '_', title)[:30]
        entry = f"@{entry_type}{{{key},\n"
        entry += f"  title = {{{title}}},\n"
        entry += f"  author = {{{author_field}}},\n"
        if year:
            entry += f"  year = {{{year}}},\n"
        if doi and doi != "unknown":
            entry += f"  doi = {{{doi}}},\n"
        if journal:
            entry += f"  journal = {{{journal}}},\n"
        entry += "}\n"
        entries.append(entry)
    with open(bib_path, "w", encoding="utf-8") as f:
        f.write("\n".join(entries))
    logger.info(f"BibTeX file saved to {bib_path}")


# ----------------------------------------------------------------------
# Main harvester
# ----------------------------------------------------------------------
async def harvest(
    keywords: List[str],
    max_results: int = 100_000,
    output_dir: str = "./corpus_output",
    max_concurrent: int = 10,
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
    email: Optional[str] = None,
    delay: float = 3.0,
    sources: str = "both",
    min_citations: Optional[int] = None,
    max_dwn_cites: Optional[int] = None,
    journal_filter_csv: Optional[str] = None,
    journal_mode: str = "block",
    doi_file: Optional[str] = None,
    parse_html: Optional[str] = None,
    skip_words: Optional[List[str]] = None,
    max_dwn_year: Optional[int] = None,
    cites: Optional[str] = None,
    ai_relevance: Optional[int] = None,
    ai_expand: bool = False,
    ai_summarise: bool = False,
    return_papers: bool = False,
    no_download: bool = False,
) -> dict:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Auto-start Ollama if any AI feature requested
    ai_requested = any([ai_relevance is not None and ai_relevance > 0, ai_expand, ai_summarise])
    _ = ensure_ollama_running(ai_requested)

    # Load email from config/env
    if email is None:
        import os
        email = os.environ.get("SCHOLAHERV_UNPAYWALL_EMAIL") or "researcher@example.com"
        try:
            cfg = load_config()
            if cfg.unpaywall and cfg.unpaywall.email:
                email = cfg.unpaywall.email
        except Exception:
            pass

    # ------------------------------------------------------------------
    # DOI file / HTML input
    # ------------------------------------------------------------------
    if doi_file or parse_html:
        paper_dois = []
        if doi_file:
            logger.info(f"Loading DOIs from file: {doi_file}")
            paper_dois = _read_doi_file(doi_file)
        elif parse_html:
            async with aiohttp.ClientSession() as sess:
                try:
                    async with sess.get(parse_html, timeout=15) as resp:
                        html = await resp.text()
                except Exception:
                    with open(parse_html, 'r', encoding='utf-8') as f:
                        html = f.read()
            paper_dois = _extract_dois(html)

        if not paper_dois:
            logger.warning("No DOIs found in provided input.")
            return {"found": 0, "downloaded": 0, "output": str(output_path)}

        all_papers = [{
            "doi": doi,
            "title": "",
            "authors": [],
            "year": None,
            "source": "doi_file",
            "pdf_url": None,
            "citation_count": 0,
            "journal": None,
        } for doi in paper_dois]

        logger.info(f"Enriching {len(all_papers)} DOIs with Unpaywall...")
        all_papers = await _enrich_unpaywall(all_papers, email, delay)

        if min_citations or max_dwn_cites or journal_filter_csv:
            logger.warning("Citation/journal filtering requested with DOI input – ignored.")

        seen_doi = set()
        unique = []
        for paper in all_papers:
            doi = paper.get("doi")
            if doi and doi not in seen_doi:
                seen_doi.add(doi)
                unique.append(paper)

        with_pdf = [p for p in unique if p.get("pdf_url")]
        logger.info(f"DOIs with a PDF: {len(with_pdf)}")

        if not with_pdf:
            logger.warning("No PDFs found for the given DOIs.")
            return {"found": len(unique), "downloaded": 0, "output": str(output_path)}

        downloaded = []
        if not no_download:
            logger.info("Starting download...")
            manager = DownloadManager(output_dir=output_path, max_concurrent=max_concurrent)
            downloaded = await manager.download_papers(with_pdf)

            # AI summarisation (DOI branch)
            if ai_summarise and downloaded:
                logger.info("Generating AI summaries for downloaded papers...")
                from schola_herv.ai.summariser import summarise_papers
                await summarise_papers(with_pdf, concurrency=1)
                logger.info("AI summaries generated.")

            # Reports (DOI branch)
            _write_markdown_report(output_path, with_pdf, {
                "found": len(unique), "downloaded": len(downloaded), "output": str(output_path)
            })
            _write_csv_report(output_path, with_pdf)
            _write_bibtex(output_path, with_pdf)

        # Cleanup Ollama if we started it
        from schola_herv.ai.ollama_manager import stop_ollama
        stop_ollama()

        if return_papers:
            return {
                "found": len(unique),
                "downloaded": len(downloaded) if not no_download else 0,
                "output": str(output_path),
                "papers": with_pdf,
                "downloaded_papers": downloaded if not no_download else [],
            }
        return {
            "found": len(unique),
            "downloaded": len(downloaded) if not no_download else 0,
            "output": str(output_path),
        }

    # ------------------------------------------------------------------
    # Citation-based discovery (--cites)
    # ------------------------------------------------------------------
    if cites:
        logger.info(f"Fetching papers that cite: {cites}")
        s2 = SemanticScholarSearcher(delay=1.0)
        citing_papers = await s2.search_citing(
            paper_id=cites,
            year_start=year_start,
            year_end=year_end,
            max_results=max_results,
        )
        logger.info(f"Found {len(citing_papers)} citing papers.")
        citing_papers = await _enrich_unpaywall(citing_papers, email, delay)
        all_papers = citing_papers

    # ------------------------------------------------------------------
    # Normal keyword discovery
    # ------------------------------------------------------------------
    else:
        # AI query expansion
        if ai_expand:
            from schola_herv.ai.query_expander import expand_query
            logger.info("Expanding query using local LLM...")
            expanded = await expand_query(keywords, num_queries=20)
            logger.info(f"Generated {len(expanded)} queries.")
            keywords = expanded

        all_papers = []

        use_arxiv = sources in ("arxiv", "both", "all")
        use_crossref = sources in ("crossref", "both", "all")
        use_openalex = sources in ("openalex", "all")
        use_core = sources in ("core", "all")

        if use_arxiv:
            logger.info("Searching ArXiv...")
            arxiv_papers = await _search_arxiv(keywords, max_results, year_start, year_end, delay)
            logger.info(f"ArXiv returned {len(arxiv_papers)} papers.")
            all_papers.extend(arxiv_papers)

        if use_crossref:
            crossref_limit = max(0, max_results - len(all_papers))
            if crossref_limit > 0:
                logger.info("Searching Crossref...")
                crossref_papers = await _search_crossref(
                    keywords, crossref_limit, year_start, year_end, email, 1.0
                )
                logger.info(f"Crossref returned {len(crossref_papers)} papers.")
                if crossref_papers:
                    logger.info("Enriching Crossref papers with Unpaywall...")
                    crossref_papers = await _enrich_unpaywall(crossref_papers, email, delay)
                    oa_count = sum(1 for p in crossref_papers if p.get("pdf_url"))
                    logger.info(f"Unpaywall found OA PDFs for {oa_count} papers.")
                all_papers.extend(crossref_papers)

        if use_openalex:
            oa_limit = max(0, max_results - len(all_papers))
            if oa_limit > 0:
                logger.info("Searching OpenAlex...")
                oa_searcher = OpenAlexSearcher(email=email, delay=1.0)
                oa_papers = await oa_searcher.search(
                    topics=keywords,
                    year_start=year_start,
                    year_end=year_end,
                    max_results=oa_limit,
                )
                logger.info(f"OpenAlex returned {len(oa_papers)} papers.")
                all_papers.extend(oa_papers)

        if use_core:
            core_limit = max(0, max_results - len(all_papers))
            if core_limit > 0:
                logger.info("Searching CORE...")
                core_searcher = CoreSearcher(email=email, delay=1.0)
                core_papers = await core_searcher.search(
                    topics=keywords,
                    year_start=year_start,
                    year_end=year_end,
                    max_results=core_limit,
                )
                logger.info(f"CORE returned {len(core_papers)} papers.")
                all_papers.extend(core_papers)

    # ------------------------------------------------------------------
    # Pipeline continues for ALL discovery methods
    # ------------------------------------------------------------------
    seen_doi = set()
    unique = []
    for paper in all_papers:
        doi = paper.get("doi")
        if doi:
            if doi not in seen_doi:
                seen_doi.add(doi)
                unique.append(paper)
        else:
            unique.append(paper)

    logger.info(f"Unique papers before filters: {len(unique)}")

    # AI relevance screening
    if ai_relevance is not None and ai_relevance > 0:
        logger.info(f"Screening papers by relevance (threshold ≥ {ai_relevance})...")
        from schola_herv.ai.relevance_filter import filter_by_relevance
        topic_text = " ".join(keywords) if keywords else "research topic"
        unique = await filter_by_relevance(unique, topic=topic_text, threshold=ai_relevance)
        logger.info(f"After AI screening: {len(unique)} papers remain.")

    if skip_words:
        logger.info(f"Applying skip-words filter: {', '.join(skip_words)}")
        unique = _apply_skip_words(unique, skip_words)
        logger.info(f"After skip-words: {len(unique)} papers remain.")

    if max_dwn_year is not None:
        logger.info(f"Applying year filter: keeping {max_dwn_year} most recent papers")
        unique = _apply_year_filter(unique, max_dwn_year)
        logger.info(f"After year filter: {len(unique)} papers remain.")

    if journal_filter_csv is not None:
        logger.info(f"Applying journal filter: {journal_filter_csv} (mode={journal_mode})")
        from schola_herv.quality.journal_filter import filter_by_journal
        unique = filter_by_journal(unique, journal_filter_csv, journal_mode)
        logger.info(f"After journal filter: {len(unique)} papers remain.")

    if min_citations is not None or max_dwn_cites is not None:
        logger.info("Fetching citation counts from Semantic Scholar...")
        unique = await _enrich_citations(unique)
        unique = _apply_citation_filter(unique, min_citations, max_dwn_cites)
        logger.info(f"After citation filter: {len(unique)} papers remain.")

    with_pdf = [p for p in unique if p.get("pdf_url")]
    logger.info(f"Papers with a PDF: {len(with_pdf)}")

    if not with_pdf:
        logger.warning("No PDFs found. Try broader keywords or include ArXiv.")
        from schola_herv.ai.ollama_manager import stop_ollama
        stop_ollama()
        return {"found": len(unique), "downloaded": 0, "output": str(output_path)}

    # Download (only if not no_download)
    downloaded = []
    if not no_download:
        logger.info("Starting download...")
        manager = DownloadManager(output_dir=output_path, max_concurrent=max_concurrent)
        downloaded = await manager.download_papers(with_pdf)

        # AI summarisation (keyword branch)
        if ai_summarise and downloaded:
            logger.info("Generating AI summaries for downloaded papers...")
            from schola_herv.ai.summariser import summarise_papers
            await summarise_papers(with_pdf, concurrency=5)
            logger.info("AI summaries generated.")

        # Reports (keyword branch)
        _write_markdown_report(output_path, with_pdf, {
            "found": len(unique), "downloaded": len(downloaded), "output": str(output_path)
        })
        _write_csv_report(output_path, with_pdf)
        _write_bibtex(output_path, with_pdf)

    # Cleanup Ollama
    from schola_herv.ai.ollama_manager import stop_ollama
    stop_ollama()

    if return_papers:
        return {
            "found": len(unique),
            "downloaded": len(downloaded) if not no_download else 0,
            "output": str(output_path),
            "papers": with_pdf,
            "downloaded_papers": downloaded if not no_download else [],
        }
    return {
        "found": len(unique),
        "downloaded": len(downloaded) if not no_download else 0,
        "output": str(output_path),
    }


# ----------------------------------------------------------------------
# Citation enrichment & filtering
# ----------------------------------------------------------------------
async def _enrich_citations(papers: List[dict]) -> List[dict]:
    doi_map = {}
    for p in papers:
        doi = p.get("doi")
        if doi:
            doi_map[doi.lower()] = p

    if doi_map:
        ids = [f"DOI:{doi}" for doi in doi_map]
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(S2_BATCH, json={"ids": ids}, timeout=60) as resp:
                    if resp.status == 200:
                        results = await resp.json()
                        for item in results:
                            if item is None:
                                continue
                            external_ids = item.get("externalIds", {})
                            doi = (external_ids.get("DOI") or "").lower()
                            if doi in doi_map:
                                doi_map[doi]["citation_count"] = item.get("citationCount", 0)
            except Exception as e:
                logger.warning(f"Semantic Scholar batch request failed: {e}")

    for p in papers:
        if "citation_count" not in p:
            p["citation_count"] = 0
    return papers


def _apply_citation_filter(papers: List[dict], min_cites: Optional[int], max_dwn: Optional[int]) -> List[dict]:
    if min_cites is not None:
        papers = [p for p in papers if p.get("citation_count", 0) >= min_cites]
    if max_dwn is not None and max_dwn > 0:
        papers = sorted(papers, key=lambda p: p.get("citation_count", 0), reverse=True)
        papers = papers[:max_dwn]
    return papers


# ----------------------------------------------------------------------
# ArXiv search (pagination, IPv4 forced)
# ----------------------------------------------------------------------
async def _search_arxiv(
    keywords: List[str],
    max_results: int,
    year_start: Optional[int],
    year_end: Optional[int],
    delay: float,
) -> List[dict]:
    query = ' OR '.join(f'all:"{kw}"' for kw in keywords)
    papers = []
    start = 0
    batch_size = 100

    connector = aiohttp.TCPConnector(family=socket.AF_INET)
    timeout_obj = aiohttp.ClientTimeout(total=120)

    async with aiohttp.ClientSession(
        headers={"User-Agent": "Schola-Herv/1.0 (mailto:researcher@example.com)"},
        connector=connector,
        timeout=timeout_obj,
    ) as session:
        while len(papers) < max_results:
            params = {
                "search_query": query,
                "start": start,
                "max_results": min(batch_size, max_results - len(papers)),
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
            await asyncio.sleep(delay)
            try:
                async with session.get(ARXIV_API, params=params, timeout=60) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(10)
                        continue
                    xml = await resp.text()
                    batch = _parse_arxiv_xml(xml, year_start, year_end)
                    if not batch:
                        break
                    papers.extend(batch)
                    start += len(batch)
                    if len(batch) < params["max_results"]:
                        break
            except aiohttp.ClientError as e:
                logger.error(f"ArXiv HTTP error: {e}")
                break
            except asyncio.TimeoutError:
                logger.error("ArXiv request timed out")
                break
            except Exception as e:
                logger.error(f"ArXiv request failed ({type(e).__name__}): {e}")
                break
    return papers[:max_results]


def _parse_arxiv_xml(xml: str, year_start: int, year_end: int) -> List[dict]:
    papers = []
    entries = xml.split('<entry>')[1:]
    for entry in entries:
        title = _xml_tag(entry, 'title')
        authors = re.findall(r'<name>(.*?)</name>', entry)
        year_str = _xml_tag(entry, 'published')[:4]
        year = int(year_str) if year_str.isdigit() else None
        if year and ((year_start and year < year_start) or (year_end and year > year_end)):
            continue
        doi = _xml_tag(entry, 'arxiv:doi')
        pdf_url = None
        for part in entry.split('<link '):
            if 'title="pdf"' in part or "title='pdf'" in part:
                m = re.search(r'''href=["']([^"']+)["']''', part)
                if m:
                    pdf_url = m.group(1)
                    break
        arxiv_id = _xml_tag(entry, 'id').split('/abs/')[-1]
        abstract = _xml_tag(entry, 'summary').strip()
        papers.append({
            'title': title.strip(),
            'authors': authors if authors else ['Unknown'],
            'year': year,
            'doi': doi if doi else None,
            'pdf_url': pdf_url,
            'source': 'arxiv',
            'id': arxiv_id,
            'abstract': abstract,
            'journal': None,
        })
    return papers


def _xml_tag(xml: str, tag: str) -> str:
    m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', xml, re.DOTALL)
    return re.sub(r'<[^>]+>', '', m.group(1)) if m else ""


# ----------------------------------------------------------------------
# Crossref search (with journal name)
# ----------------------------------------------------------------------
async def _search_crossref(
    keywords: List[str],
    max_results: int,
    year_start: Optional[int],
    year_end: Optional[int],
    email: str,
    delay: float,
) -> List[dict]:
    query = " ".join(keywords)
    papers = []
    cursor = "*"
    page_size = min(200, max_results)
    last_request = 0

    async with aiohttp.ClientSession(
        headers={"User-Agent": f"Schola-Herv/1.0 (mailto:{email})"}
    ) as session:
        while len(papers) < max_results:
            now = time.monotonic()
            elapsed = now - last_request
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
            last_request = time.monotonic()
            params = {
                "query": query,
                "cursor": cursor,
                "rows": page_size,
                "sort": "relevance",
            }
            if year_start:
                params["filter"] = f"from-pub-date:{year_start}-01-01"
            if year_end:
                params["filter"] = (
                    f"{params.get('filter', '')}until-pub-date:{year_end}-12-31"
                ).strip()
            try:
                async with session.get(CROSSREF_API, params=params, timeout=60) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(5)
                        continue
                    if resp.status != 200:
                        logger.error(f"Crossref request failed with status {resp.status}")
                        break
                    data = await resp.json()
                    if not isinstance(data, dict):
                        logger.warning("Unexpected Crossref response (not a dict), skipping page.")
                        break
                    items = data.get("message", {}).get("items", [])
                    if not items:
                        break
                    for item in items:
                        paper = _parse_crossref_item(item)
                        if paper:
                            papers.append(paper)
                            if len(papers) >= max_results:
                                break
                    cursor = data.get("message", {}).get("next-cursor")
                    if not cursor or len(items) < page_size:
                        break
            except aiohttp.ClientError:
                await asyncio.sleep(2)
                continue
    return papers


def _parse_crossref_item(item: dict) -> Optional[dict]:
    try:
        title = (item.get("title") or ["No title"])[0]
        authors = []
        for a in item.get("author", []):
            given = a.get("given", "")
            family = a.get("family", "")
            if family:
                authors.append(f"{family}, {given}".strip(", "))
            elif given:
                authors.append(given)
        year = None
        for date_part in ["published-print", "published-online", "created"]:
            y = item.get(date_part, {}).get("date-parts", [[None]])[0]
            if y and y[0]:
                year = y[0]
                break

        journal = None
        container = item.get("container-title")
        if container:
            journal = container[0] if isinstance(container, list) else container

        return {
            "title": title,
            "authors": authors if authors else ["Unknown"],
            "year": int(year) if year else None,
            "doi": item.get("DOI"),
            "pdf_url": None,
            "source": "crossref",
            "journal": journal,
        }
    except Exception:
        return None


# ----------------------------------------------------------------------
# Unpaywall enrichment
# ----------------------------------------------------------------------
async def _enrich_unpaywall(papers: List[dict], email: str, delay: float) -> List[dict]:
    sem = asyncio.Semaphore(1)

    async def enrich_one(session, paper):
        doi = paper.get("doi")
        if not doi:
            return paper
        async with sem:
            await asyncio.sleep(delay)
            url = UNPAYWALL_API.format(doi=doi, email=email)
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        best = data.get("best_oa_location")
                        if best and best.get("url_for_pdf"):
                            paper["pdf_url"] = best["url_for_pdf"]
            except Exception:
                pass
        return paper

    async with aiohttp.ClientSession() as session:
        tasks = [enrich_one(session, p) for p in papers]
        enriched = []
        for coro in asyncio.as_completed(tasks):
            enriched.append(await coro)
    return enriched