"""
Interactive interview wizard for Schola-herv.
Uses Rich prompts to build a complete Job configuration.
"""

from typing import List, Optional
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from schola_herv.jobs import Job

SUPPORTED_SOURCES = ['arxiv', 'crossref', 'openalex', 'core', 'both', 'all']


def get_user_preferences(console: Console) -> Optional[Job]:
    console.print("\n[bold cyan]Welcome to Schola-herv![/bold cyan]")
    console.print("Let's set up your paper harvesting job.\n")

    # 1. Task type
    console.print("[bold]What would you like to do?[/bold]")
    console.print("[1] Discover papers only (save metadata)")
    console.print("[2] Discover and download PDFs (full pipeline)")
    task_choice = Prompt.ask("Choice", choices=['1', '2'], default='2')
    task = 'full' if task_choice == '2' else 'discover'

    # 2. Sources
    console.print(f"\n[bold]Select sources[/bold]")
    console.print(f"  Options: {', '.join(SUPPORTED_SOURCES)}")
    console.print("  'all' = arxiv + crossref + openalex + core")
    console.print("  'both' = arxiv + crossref + openalex")
    sources_input = Prompt.ask("Sources", default="all").strip().lower()
    selected = [s.strip() for s in sources_input.split(',') if s.strip()]
    sources = []
    if 'all' in selected:
        sources = ['arxiv', 'crossref', 'openalex', 'core']
    elif 'both' in selected:
        sources = ['arxiv', 'crossref', 'openalex']
    else:
        for s in selected:
            if s in SUPPORTED_SOURCES and s not in ('both', 'all'):
                sources.append(s)
    if not sources:
        console.print("[red]No valid sources selected. Aborting.[/red]")
        return None
    console.print(f"  Using: [green]{', '.join(sources)}[/green]")

    # 3. Research topics
    console.print("\n[bold]Enter research topics/areas[/bold] (comma-separated)")
    console.print("Example: 'machine learning, natural language processing, transformers'")
    topics_input = Prompt.ask("Topics").strip()
    if not topics_input:
        console.print("[red]Topics are required. Aborting.[/red]")
        return None
    topics = [t.strip() for t in topics_input.split(',') if t.strip()]

    # 4. Additional keywords
    console.print("\n[bold]Additional keywords?[/bold] (optional, comma-separated, press Enter to skip)")
    keywords_input = Prompt.ask("Keywords", default="").strip()
    keywords = [k.strip() for k in keywords_input.split(',') if k.strip()] if keywords_input else []

    # 5. Date range
    console.print("\n[bold]Date range[/bold] (press Enter to skip)")
    year_start = IntPrompt.ask("Start year (blank = no limit)", default=None, show_default=False)
    year_end = IntPrompt.ask("End year (blank = no limit)", default=None, show_default=False)
    if year_start and year_end and year_start > year_end:
        console.print("[red]Start year must be before end year. Swapping.[/red]")
        year_start, year_end = year_end, year_start

    # 6. Max papers
    console.print("\n[bold]How many papers do you want?[/bold]")
    max_papers = IntPrompt.ask("Number of papers", default=100)

    # 7. Output directory
    console.print("\n[bold]Where should the output be saved?[/bold]")
    output_dir = Prompt.ask("Output directory", default="./corpus_output").strip()

    # 8. Concurrent downloads
    console.print("\n[bold]Maximum concurrent downloads?[/bold]")
    max_concurrent = IntPrompt.ask("Concurrent downloads", default=10)

    # ---- ADVANCED OPTIONS ----
    console.print("\n[bold yellow]Advanced filtering (press Enter to skip any)[/bold yellow]")

    # Skip words
    skip_input = Prompt.ask("  Words to skip in title/abstract (comma-separated)", default="").strip()
    skip_words = [w.strip() for w in skip_input.split(',') if w.strip()] if skip_input else []

    # Max most recent papers
    max_dwn_year = IntPrompt.ask("  Keep only N most recent papers (blank = no limit)", default=None, show_default=False)

    # Minimum citations
    min_cit = IntPrompt.ask("  Minimum citations required (blank = any)", default=None, show_default=False)

    # Top N by citations
    top_cites = IntPrompt.ask("  Keep only top N most-cited papers (blank = all)", default=None, show_default=False)

    # Journal filter
    journal_csv = Prompt.ask("  Journal filter CSV file (blank = none)", default="").strip() or None
    journal_mode = "block"
    if journal_csv:
        mode = Prompt.ask("  Journal filter mode? [block/allow]", choices=["block", "allow"], default="block")
        journal_mode = mode

    # Citation-based discovery
    cites_doi = Prompt.ask("  Landmark paper DOI (--cites) – download all papers that cite this DOI (blank = skip)", default="").strip() or None
    if cites_doi:
        # If cites is given, topics can be empty (but we already have them, they'll be ignored)
        pass

    # 9. Job name
    console.print("\n[bold]Give this job a name?[/bold] (optional)")
    job_name = Prompt.ask("Job name", default="").strip() or None

    # Summary
    console.print("\n[bold yellow]Summary:[/bold yellow]")
    console.print(f"  Task:           {task}")
    console.print(f"  Sources:        {', '.join(sources)}")
    console.print(f"  Topics:         {', '.join(topics)}")
    if keywords:
        console.print(f"  Keywords:       {', '.join(keywords)}")
    console.print(f"  Date range:     {year_start or 'any'} → {year_end or 'any'}")
    console.print(f"  Max papers:     {max_papers}")
    console.print(f"  Output:         {output_dir}")
    console.print(f"  Concurrency:    {max_concurrent}")
    if skip_words:
        console.print(f"  Skip words:     {', '.join(skip_words)}")
    if max_dwn_year:
        console.print(f"  Max recent:     {max_dwn_year}")
    if min_cit is not None:
        console.print(f"  Min citations:  {min_cit}")
    if top_cites:
        console.print(f"  Top N cited:    {top_cites}")
    if journal_csv:
        console.print(f"  Journal filter: {journal_csv} (mode={journal_mode})")
    if cites_doi:
        console.print(f"  Cites landmark: {cites_doi}")
    if job_name:
        console.print(f"  Job name:       {job_name}")

    if not Confirm.ask("\nProceed with this configuration?", default=True):
        console.print("[red]Aborted.[/red]")
        return None

    return Job(
        topics=topics,
        sources=sources,
        keywords=keywords,
        year_start=year_start,
        year_end=year_end,
        max_papers=max_papers,
        output_dir=output_dir,
        task=task,
        max_concurrent=max_concurrent,
        job_name=job_name,
        skip_words=skip_words,
        max_dwn_year=max_dwn_year,
        min_citations=min_cit,
        max_dwn_cites=top_cites,
        journal_filter_csv=journal_csv,
        journal_mode=journal_mode,
        cites=cites_doi,
    )