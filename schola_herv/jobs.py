"""
Job definition and persistence for Schola-herv.

A Job captures everything needed to reproduce a corpus building run.
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass
class Job:
    """
    Represents a single corpus-building job.
    """
    # Required
    topics: List[str]                          # e.g. ["machine learning", "synchrotron radiation"]

    # Sources
    sources: List[str] = field(default_factory=lambda: ["arxiv", "pubmed"])

    # Search filters
    keywords: List[str] = field(default_factory=list)  # additional keywords
    year_start: Optional[int] = None
    year_end: Optional[int] = None

    # Volume
    max_papers: int = 100

    # Output
    output_dir: str = "./corpus_output"

    # Task type
    task: str = "full"                         # "discover", "download", "full"

    # Download settings
    max_concurrent: int = 10
    resume: bool = True

    # Metadata
    job_name: Optional[str] = None
    description: Optional[str] = None

    # ----------------------------------------------------------------
    # ADVANCED FILTERS (added for Wave 1 & 2)
    # ----------------------------------------------------------------
    skip_words: List[str] = field(default_factory=list)      # words to skip in title/abstract
    max_dwn_year: Optional[int] = None                      # keep N most recent papers
    min_citations: Optional[int] = None                     # minimum citations required
    max_dwn_cites: Optional[int] = None                     # top N cited papers
    journal_filter_csv: Optional[str] = None                # CSV file for journal names/ISSNs
    journal_mode: str = "block"                             # "block" or "allow"
    cites: Optional[str] = None                             # DOI of a landmark paper to find citations
    doi_file: Optional[str] = None                          # path to a file containing DOIs
    parse_html: Optional[str] = None                        # path or URL to an HTML file with DOIs

    def to_dict(self) -> dict:
        """Convert job to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        """Create a Job from a dictionary."""
        # Keep only fields that are defined in the dataclass
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def save(self, path: str = None) -> Path:
        """
        Save the job to a YAML file.

        Args:
            path: Path to save the YAML file. If None, auto-generate from job_name.

        Returns:
            Path object pointing to the saved file.
        """
        if path is None:
            job_dir = Path(self.output_dir)
            job_dir.mkdir(parents=True, exist_ok=True)
            name = self.job_name or "job"
            path = job_dir / f"{name}.yaml"
        else:
            path = Path(path)

        with open(path, 'w') as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)
        return path

    @classmethod
    def load(cls, path: str) -> "Job":
        """
        Load a job from a YAML file.

        Args:
            path: Path to the YAML file.

        Returns:
            Job instance.
        """
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)


# For easy creation in interactive mode
def create_job(**kwargs) -> Job:
    """Create a Job with sensible defaults, overriding with provided kwargs."""
    return Job(**kwargs)