"""
Resumable-download checkpoint — O(1) lookup, atomic disk writes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger("schola_herv.downloader.checkpoint")

_KEY_DOWNLOADED = "downloaded"
_KEY_FAILED     = "failed"


class Checkpoint:
    """
    Persists the set of downloaded and failed paper identifiers to a JSON file.
    Uses sets internally for O(1) membership tests and writes atomically
    (tmp-file + rename) to prevent corruption.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._downloaded: set[str] = set()
        self._failed: set[str] = set()
        self._load()

    # ------------------------------------------------------------------ load/save

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._downloaded = set(data.get(_KEY_DOWNLOADED, []))
            self._failed     = set(data.get(_KEY_FAILED, []))
        except Exception as exc:
            logger.warning(f"Could not read checkpoint {self.path}: {exc}. Starting fresh.")

    def _save(self) -> None:
        try:
            payload = json.dumps(
                {_KEY_DOWNLOADED: sorted(self._downloaded),
                 _KEY_FAILED:     sorted(self._failed)},
                indent=2,
            )
            tmp = self.path.with_suffix(".tmp")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self.path)          # atomic on POSIX; best-effort on Windows
        except Exception as exc:
            logger.error(f"Failed to save checkpoint {self.path}: {exc}")

    # ------------------------------------------------------------------ public API

    def is_downloaded(self, identifier: str) -> bool:
        return identifier in self._downloaded

    def mark_downloaded(self, identifier: str) -> None:
        self._downloaded.add(identifier)
        self._failed.discard(identifier)
        self._save()

    def mark_failed(self, identifier: str) -> None:
        if identifier not in self._downloaded:
            self._failed.add(identifier)
            self._save()

    def stats(self) -> Dict[str, int]:
        return {"downloaded": len(self._downloaded), "failed": len(self._failed)}

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def paper_identifier(paper: dict) -> str:
        """
        Stable, unique key for a paper.
        Prefers DOI; falls back to a normalised title+year string.
        Includes a short hash of the title to reduce collisions.
        """
        doi = paper.get("doi")
        if doi:
            return f"doi:{doi.strip().lower()}"
        title = paper.get("title", "untitled")
        year  = paper.get("year", "0")
        slug  = "".join(c for c in title.lower() if c.isalnum() or c == " ")[:80]
        import hashlib
        h = hashlib.md5(title.encode()).hexdigest()[:8]
        return f"title:{slug}_{year}_{h}"
