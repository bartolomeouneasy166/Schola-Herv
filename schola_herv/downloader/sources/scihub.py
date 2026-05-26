"""
Sci‑Hub fallback downloader. Use with caution.
Sci‑Hub might be illegal in some jurisdictions. Users are solely responsible.
"""

import aiohttp
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup

from .base import BaseDownloader
from schola_herv.utils.pdf_utils import generate_filename, verify_pdf

SCI_HUB_URL = "https://sci-hub.se"


class SciHubDownloader(BaseDownloader):
    async def can_handle(self, paper: dict) -> bool:
        return bool(paper.get("doi"))

    async def download(
        self, session: aiohttp.ClientSession, paper: dict, output_dir: Path
    ) -> Optional[Path]:
        doi = paper["doi"]
        filename = generate_filename(paper)
        filepath = output_dir / filename
        if filepath.exists() and verify_pdf(filepath):
            return filepath

        try:
            async with session.get(f"{SCI_HUB_URL}/{doi}", timeout=30) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')

                # Look for embedded PDF
                embed = soup.find('embed', type='application/pdf')
                if embed and embed.get('src'):
                    pdf_url = embed['src']
                    if pdf_url.startswith('//'):
                        pdf_url = 'https:' + pdf_url
                    elif pdf_url.startswith('/'):
                        pdf_url = SCI_HUB_URL + pdf_url
                    async with session.get(pdf_url, timeout=30) as pdf_resp:
                        if pdf_resp.status == 200:
                            content = await pdf_resp.read()
                            filepath.write_bytes(content)
                            if verify_pdf(filepath):
                                return filepath

                # Fallback: button with onclick redirect
                button = soup.find('button', onclick=True)
                if button:
                    import re
                    match = re.search(r"location\.href='(.*?)'", button['onclick'])
                    if match:
                        pdf_url = match.group(1)
                        if pdf_url.startswith('//'):
                            pdf_url = 'https:' + pdf_url
                        async with session.get(pdf_url, timeout=30) as pdf_resp:
                            if pdf_resp.status == 200:
                                content = await pdf_resp.read()
                                filepath.write_bytes(content)
                                if verify_pdf(filepath):
                                    return filepath
        except Exception:
            pass
        return None