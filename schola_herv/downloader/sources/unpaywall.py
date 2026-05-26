"""
Unpaywall PDF downloader.

The actual download logic is identical to the generic URL downloader —
the distinction is made upstream when Unpaywall enriches paper metadata
with the ``pdf_url`` field.  This module exists for backward compatibility.
"""
from schola_herv.downloader.sources.direct import UrlDownloader

# Alias kept for backward compatibility
UnpaywallDownloader = UrlDownloader

__all__ = ["UnpaywallDownloader", "UrlDownloader"]
