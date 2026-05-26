#!/usr/bin/env python3
"""
Schola-herv command-line interface.
"""

import argparse
import asyncio
import sys
import yaml
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from schola_herv.config import load_config
from schola_herv.interview import get_user_preferences
from schola_herv.jobs import Job
from schola_herv.discovery.arxiv import ArxivSearcher
from schola_herv.discovery.pubmed import PubMedSearcher
from schola_herv.discovery.crossref import CrossrefSearcher
from schola_herv.discovery.unpaywall import UnpaywallEnricher
from schola_herv.downloader.manager import DownloadManager
from schola_herv.utils.logger import setup_logger

console = Console()
logger = setup_logger()


# ---------------------------------------------------------------------------
# Old discovery helper (used by discover command)
# ---------------------------------------------------------------------------
async def discover_papers(job: Job) -> list[dict]:
    searchers = {
        'arxiv': ArxivSearcher(),
        'pubmed': PubMedSearcher(),
        'crossref': CrossrefSearcher(),
    }
    all_papers = []
    for src in job.sources:
        if src not in searchers:
            console.print(f"[red]Unknown source '{src}', skipping[/red]")
            continue
        console.print(f"  Searching [bold]{src}[/bold]...")
        try:
            searcher = searchers[src]
            papers = await searcher.search(
                topics=job.topics,
                keywords=job.keywords,
                year_start=job.year_start,
                year_end=job.year_end,
                max_results=job.max_papers // len(job.sources),
            )
            console.print(f"    Found {len(papers)} papers from {src}")
            all_papers.extend(papers)
        except Exception as e:
            logger.error(f"Search failed for {src}: {e}")
            console.print(f"  [red]Error: {e}[/red]")
    if not all_papers:
        return []
    seen_doi = set()
    unique = []
    for paper in all_papers:
        doi = paper.get('doi')
        if doi:
            if doi not in seen_doi:
                seen_doi.add(doi)
                unique.append(paper)
        else:
            norm = paper['title'].lower().strip()
            if not any(p['title'].lower().strip() == norm for p in unique):
                unique.append(paper)
    console.print("  Enriching with open-access PDF links (Unpaywall)...")
    enricher = UnpaywallEnricher(email="researcher@example.com")
    enriched = await enricher.enrich(unique)
    return enriched[:job.max_papers]


# ---------------------------------------------------------------------------
# New interactive runner (uses the harvester)
# ---------------------------------------------------------------------------
async def run_interactive(args):
    console.print(Panel.fit(
        "[bold cyan]Schola-herv[/bold cyan]\n"
        "Scholarly Paper Harvester for LLM Corpora",
        border_style="cyan"
    ))
    job = get_user_preferences(console)
    if not job:
        console.print("[red]Job creation cancelled.[/red]")
        return

    job_path = job.save()
    console.print(f"[green]Job saved to {job_path}[/green]")

    from schola_herv.harvester import harvest

    # Map sources for the harvester
    # The harvester expects a string: 'arxiv', 'crossref', 'openalex', 'core', 'both', 'all'
    # We already have the expanded list; determine the right string
    if set(job.sources) >= {'arxiv', 'crossref', 'openalex', 'core'}:
        src = "all"
    elif set(job.sources) >= {'arxiv', 'crossref', 'openalex'}:
        src = "both"
    elif 'arxiv' in job.sources and len(job.sources) == 1:
        src = "arxiv"
    elif 'crossref' in job.sources and len(job.sources) == 1:
        src = "crossref"
    elif 'openalex' in job.sources and len(job.sources) == 1:
        src = "openalex"
    elif 'core' in job.sources and len(job.sources) == 1:
        src = "core"
    else:
        src = "all"  # fallback

    result = await harvest(
        keywords=job.topics + job.keywords,
        max_results=job.max_papers,
        output_dir=job.output_dir,
        max_concurrent=job.max_concurrent,
        year_start=job.year_start,
        year_end=job.year_end,
        sources=src,
        min_citations=job.min_citations,
        max_dwn_cites=job.max_dwn_cites,
        journal_filter_csv=job.journal_filter_csv,
        journal_mode=job.journal_mode,
        skip_words=job.skip_words or None,
        max_dwn_year=job.max_dwn_year,
        cites=job.cites,
        doi_file=job.doi_file,
        parse_html=job.parse_html,
    )
    console.print(f"[green]Done. {result['downloaded']} PDFs downloaded to {result['output']}[/green]")


# ---------------------------------------------------------------------------
# Old discover command
# ---------------------------------------------------------------------------
async def discover_command(args):
    job = Job(
        topics=[t.strip() for t in args.topic.split(",")],
        sources=[s.strip() for s in args.source.split(",") if s.strip()],
        keywords=[k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else [],
        year_start=args.year_from,
        year_end=args.year_to,
        max_papers=args.max,
        output_dir=args.output,
        task="discover",
    )
    papers = await discover_papers(job)
    console.print(f"[green]Found {len(papers)} papers.[/green]")
    import json
    meta_path = Path(args.output) / "metadata.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w") as f:
        json.dump(papers, f, indent=2)
    console.print(f"Metadata saved to {meta_path}")


async def download_command(args):
    job = Job.load(args.job_file)
    output_dir = Path(job.output_dir)
    manager = DownloadManager(
        output_dir=output_dir,
        max_concurrent=job.max_concurrent,
    )
    papers = []
    meta_path = output_dir / "metadata.json"
    if meta_path.exists():
        import json
        with open(meta_path) as f:
            papers = json.load(f)
    else:
        console.print("[red]No metadata.json found. Run discovery first.[/red]")
        return
    downloaded = await manager.download_papers(papers)
    console.print(f"[green]Downloaded {len(downloaded)} papers.[/green]")


def serve_command(args):
    webapp_dir = Path(__file__).resolve().parent.parent / "webapp"
    sys.path.insert(0, str(webapp_dir))
    from app import app
    app.run(debug=args.debug, host=args.host, port=args.port)


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Schola-herv: Scholarly Paper Harvester")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # ---------- harvest (main command) ----------
    harvest_parser = subparsers.add_parser("harvest", help="Massive one-command PDF harvest")
    harvest_parser.add_argument("-k", "--keywords", default=None,
                                help="Comma-separated keywords (e.g. 'deep learning,GAN')")
    harvest_parser.add_argument("-m", "--max", dest="max_results", type=int,
                                default=10000, help="Maximum number of papers to download")
    harvest_parser.add_argument("-o", "--output", default="./corpus_output",
                                help="Output directory")
    harvest_parser.add_argument("--concurrent", type=int, default=10,
                                help="Max concurrent downloads")
    harvest_parser.add_argument("--year-from", type=int, default=None)
    harvest_parser.add_argument("--year-to", type=int, default=None)
    harvest_parser.add_argument("--sources", choices=["arxiv", "crossref", "openalex", "core", "pubmed", "both", "all"],
                            default="both", help="Which sources to search (arxiv, crossref, openalex, core, pubmed, both, all)")
    harvest_parser.add_argument("--min-citations", type=int, default=None,
                                help="Only download papers with at least N citations")
    harvest_parser.add_argument("--max-dwn-cites", type=int, default=None,
                                help="Download only the top N most-cited papers (after other filters)")
    harvest_parser.add_argument("--journal-filter", type=str, default=None,
                                help="CSV file of journal names/ISSNs to block or allow")
    harvest_parser.add_argument("--journal-mode", choices=["block", "allow"],
                                default="block", help="'block' (default) or 'allow'")
    harvest_parser.add_argument("--doi-file", type=str, default=None,
                                help="Path to a file containing DOIs (one per line, or CSV)")
    harvest_parser.add_argument("--parse-html", type=str, default=None,
                                help="Path or URL of an HTML file to extract DOIs from")
    harvest_parser.add_argument("--skip-words", type=str, default=None,
                                help="Comma-separated words to skip in title/abstract")
    harvest_parser.add_argument("--max-dwn-year", type=int, default=None,
                            help="Download only the top N most recent papers by publication year")
    harvest_parser.add_argument("--cites", type=str, default=None,
                            help="DOI of a landmark paper: download all papers that cite it")
    harvest_parser.add_argument("--ai-relevance", type=int, choices=[0,1,2,3,4,5], default=None,
                            help="Use local LLM to score papers; 0 = skip, 1-5 = keep papers scoring >= N")
    harvest_parser.add_argument("--ai-expand", action="store_true", default=False,
                            help="Use local LLM (Ollama) to expand keywords into 20 diverse queries")
    harvest_parser.add_argument("--ai-summarise", action="store_true", default=False,
                            help="Generate one-sentence LLM summaries for each downloaded paper")
    harvest_parser.add_argument("--recipe", type=str, default=None,
                                help="Name of a pre‑defined corpus recipe (located in schola_herv/recipes/)")
    harvest_parser.add_argument("--log-file", type=str, default=None,
                                help="Path to a log file (in addition to console output)")

    # ---------- Old commands ----------
    subparsers.add_parser("run", help="Interactive wizard and full pipeline")
    disc = subparsers.add_parser("discover", help="Discover papers (non-interactive)")
    disc.add_argument("--source", default="arxiv,pubmed", help="Comma-separated sources")
    disc.add_argument("--topic", required=True, help="Research topics (comma-separated)")
    disc.add_argument("--keywords", default="", help="Additional keywords")
    disc.add_argument("--year-from", type=int, default=None)
    disc.add_argument("--year-to", type=int, default=None)
    disc.add_argument("--max", type=int, default=100)
    disc.add_argument("--output", default="./corpus_output")
    dnl = subparsers.add_parser("download", help="Download PDFs from a job file")
    dnl.add_argument("job_file", help="Path to job YAML file")
    serve = subparsers.add_parser("serve", help="Start the web interface")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=5000)
    serve.add_argument("--debug", dest="debug", action="store_true", default=False)
    # ---------- natural language interface ----------
    ask_parser = subparsers.add_parser("ask", help="Natural language interface – describe what you want in plain English")
    ask_parser.add_argument("query", nargs="+", help="Your request in plain English")
    ask_parser.add_argument("--execute", action="store_true", default=False,
                            help="Automatically execute the translated command (otherwise just print it)")
        # ---------- survey (metadata + Excel with optional PDFs and AI) ----------
    survey_parser = subparsers.add_parser("survey",
        help="Discover papers and generate an enriched Excel file (with optional PDF download and AI features)")
    survey_parser.add_argument("-k", "--keywords", required=True,
                               help="Comma-separated keywords / domain")
    survey_parser.add_argument("--sources", choices=["arxiv","crossref","openalex","core","both","all"],
                               default="all", help="Sources to search (default: all)")
    survey_parser.add_argument("--max", dest="max_results", type=int, default=100,
                               help="Maximum papers to discover (default: 100)")
    survey_parser.add_argument("--year-from", type=int, default=None)
    survey_parser.add_argument("--year-to", type=int, default=None)
    survey_parser.add_argument("--excel-output", required=True,
                               help="Path to the output Excel file (e.g., survey.xlsx)")
    survey_parser.add_argument("--metadata-only", action="store_true", default=False,
                               help="Only generate Excel file, do not download PDFs")
    survey_parser.add_argument("--pdf-folder", type=str, default=None,
                               help="Folder to save downloaded PDFs (required unless --metadata-only)")
    survey_parser.add_argument("--scimago-csv", type=str, default=None,
                               help="Path to SCImago Journal Rank CSV (for quartile & impact factor)")
    survey_parser.add_argument("--ai-expand", action="store_true", default=False,
                               help="Use local LLM to expand keywords into diverse queries")
    survey_parser.add_argument("--ai-relevance", type=int, choices=[0,1,2,3,4,5], default=None,
                               help="Use local LLM to score papers 1-5; 0 = skip, N = keep papers scoring >= N")
    survey_parser.add_argument("--ai-summarise", action="store_true", default=False,
                               help="Generate AI summaries for each paper (adds 'AI Summary' column to Excel)")
    survey_parser.add_argument("--log-file", type=str, default=None,
                               help="Path to a log file (in addition to console output)")
    args = parser.parse_args()

    if args.command == "harvest":
        # Configure file logging if requested
        if getattr(args, "log_file", None):
            from pathlib import Path as _Path
            setup_logger(log_file=_Path(args.log_file))
        # ----- INSERT THE RECIPE BLOCK HERE -----
        if args.recipe:
            recipe_path = Path(__file__).resolve().parent / "recipes" / f"{args.recipe}.yaml"
            if not recipe_path.exists():
                console.print(f"[red]Recipe '{args.recipe}' not found at {recipe_path}[/red]")
                sys.exit(1)
            import yaml
            with open(recipe_path, 'r') as f:
                recipe = yaml.safe_load(f)
            # Merge recipe with CLI args (CLI args override recipe)
            if not args.keywords and 'keywords' in recipe:
                args.keywords = ",".join(recipe['keywords'])
            if args.sources == "both" and 'sources' in recipe:
                args.sources = recipe['sources']
            if args.max_results == 10000 and 'max_results' in recipe:
                args.max_results = int(recipe['max_results'])
            if args.year_from is None and 'year_from' in recipe:
                args.year_from = int(recipe['year_from'])
            if args.year_to is None and 'year_to' in recipe:
                args.year_to = int(recipe['year_to'])
            if args.min_citations is None and 'min_citations' in recipe:
                args.min_citations = int(recipe['min_citations'])
            if args.max_dwn_cites is None and 'max_dwn_cites' in recipe:
                args.max_dwn_cites = int(recipe['max_dwn_cites'])
            if args.skip_words is None and 'skip_words' in recipe:
                args.skip_words = ",".join(recipe['skip_words']) if isinstance(recipe['skip_words'], list) else recipe['skip_words']
            if not args.ai_expand and recipe.get('ai_expand'):
                args.ai_expand = True
            if args.ai_relevance is None and 'ai_relevance' in recipe:
                args.ai_relevance = int(recipe['ai_relevance'])
            if not args.ai_summarise and recipe.get('ai_summarise'):
                args.ai_summarise = True
        # ----- END OF RECIPE BLOCK -----
        keywords = []
        if args.keywords:
            keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

        skip_words = []
        if args.skip_words:
            skip_words = [w.strip().lower() for w in args.skip_words.split(",") if w.strip()]

        if not args.doi_file and not args.parse_html and not args.cites and not keywords:
            console.print("[red]ERROR: provide --keywords, --cites, or --doi-file / --parse-html[/red]")
            sys.exit(1)

        from schola_herv.harvester import harvest
        max_dwn_year = args.max_dwn_year
        cites_doi = args.cites
        result = asyncio.run(harvest(
            keywords=keywords,
            max_results=args.max_results,
            output_dir=args.output,
            max_concurrent=args.concurrent,
            year_start=args.year_from,
            year_end=args.year_to,
            sources=args.sources,
            min_citations=args.min_citations,
            max_dwn_cites=args.max_dwn_cites,
            journal_filter_csv=args.journal_filter,
            journal_mode=args.journal_mode,
            doi_file=args.doi_file,
            parse_html=args.parse_html,
            skip_words=skip_words,
            max_dwn_year=max_dwn_year,
            cites=cites_doi,
            ai_expand=args.ai_expand,
            ai_relevance=args.ai_relevance,
            ai_summarise=args.ai_summarise,
        ))
        console.print(f"[green]Done. {result['downloaded']} PDFs downloaded to {result['output']}[/green]")

    elif args.command == "run":
        asyncio.run(run_interactive(args))
    elif args.command == "discover":
        asyncio.run(discover_command(args))
    elif args.command == "download":
        asyncio.run(download_command(args))
    elif args.command == "serve":
        serve_command(args)
    elif args.command == "ask":
        query_text = " ".join(args.query)
        console.print(f"[bold]Translating:[/bold] {query_text}")
        from schola_herv.ai.ollama_manager import ensure_ollama_running
        ensure_ollama_running(True)
        from schola_herv.ai.natural_language import translate_natural_language
        params = asyncio.run(translate_natural_language(query_text))
        if not params:
            console.print("[red]Failed to translate the request. Please be more specific or use the regular CLI.[/red]")
            sys.exit(1)
        # Build display command
        cli_parts = ["schola-herv harvest"]
        for key, value in params.items():
            if value is None or value == [] or value is False or value == "" or (isinstance(value, dict) and not value):
                continue
            if isinstance(value, bool) and value:
                cli_parts.append(f"--{key.replace('_','-')}")
            elif isinstance(value, list):
                cli_parts.append(f"--{key.replace('_','-')} \"{','.join(value)}\"")
            elif isinstance(value, str):
                cli_parts.append(f"--{key.replace('_','-')} \"{value}\"")
            else:
                cli_parts.append(f"--{key.replace('_','-')} {value}")
        translated_command = " ".join(cli_parts)
        console.print(f"[green]Translated command:[/green] {translated_command}")

        if args.execute:
            keywords = params.get("keywords", [])
            sources = params.get("sources", "all")
            max_results = int(params.get("max_results", 100))
            output_dir = params.get("output_dir") or "./corpus_output"
            year_start = params.get("year_from")
            year_end = params.get("year_to")
            min_citations = params.get("min_citations")
            max_dwn_cites = params.get("max_dwn_cites")
            skip_words = params.get("skip_words")
            ai_relevance = params.get("ai_relevance")
            ai_summarise = bool(params.get("ai_summarise", False))
            ai_expand = bool(params.get("ai_expand", False))

            from schola_herv.harvester import harvest
            result = asyncio.run(harvest(
                keywords=keywords,
                sources=sources,
                max_results=max_results,
                output_dir=output_dir,
                year_start=year_start,
                year_end=year_end,
                min_citations=min_citations,
                max_dwn_cites=max_dwn_cites,
                skip_words=skip_words,
                ai_relevance=ai_relevance,
                ai_summarise=ai_summarise,
                ai_expand=ai_expand,
            ))
            console.print(f"[green]Done. {result['downloaded']} PDFs downloaded to {result['output']}[/green]")
        else:
            console.print("[yellow]To execute this command automatically, add --execute[/yellow]")
    elif args.command == "survey":
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
        sources = args.sources
        max_results = args.max_results
        year_start = args.year_from
        year_end = args.year_to
        metadata_only = args.metadata_only
        excel_output = args.excel_output
        scimago_csv = args.scimago_csv
        pdf_folder = args.pdf_folder or "./survey_pdfs"

        if not metadata_only and not args.pdf_folder:
            console.print("[red]ERROR: --pdf-folder is required unless --metadata-only[/red]")
            sys.exit(1)

        from schola_herv.harvester import harvest
        import asyncio

        harvest_result = asyncio.run(harvest(
            keywords=keywords,
            max_results=max_results,
            output_dir=pdf_folder,
            year_start=year_start,
            year_end=year_end,
            sources=sources,
            no_download=metadata_only,
            ai_expand=args.ai_expand,
            ai_relevance=args.ai_relevance,
            ai_summarise=args.ai_summarise,
            return_papers=True,
        ))

        papers = harvest_result.get("papers", [])
        if not papers:
            console.print("[red]No papers found. Exiting.[/red]")
            sys.exit(1)

        # Enrich with journal metrics (SCImago)
        from schola_herv.metadata_builder import load_scimago_csv, enrich_with_journal_metrics, build_excel
        scimago_data = load_scimago_csv(scimago_csv)
        papers = enrich_with_journal_metrics(papers, scimago_data)

        # Fill missing DOIs using Crossref
        from schola_herv.metadata_builder import resolve_missing_dois
        import asyncio
        papers = asyncio.run(resolve_missing_dois(papers))

        include_pdf_col = not metadata_only
        # If AI summarise was used, we can add an extra column later (stretch goal)
        excel_path = Path(excel_output)
        build_excel(papers, excel_path, include_pdf_col=include_pdf_col)
        console.print(f"[green]Survey complete. Excel file saved to {excel_path}[/green]")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()