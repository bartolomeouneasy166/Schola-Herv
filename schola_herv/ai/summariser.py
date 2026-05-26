"""
LLM summariser for downloaded papers.
"""

import asyncio
import aiohttp
from typing import List

import os
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")

SUMMARY_PROMPT = (
    "In one plain‑English sentence, summarise the main contribution of this paper.\n"
    "Title: {title}\n"
    "Abstract: {abstract}\n"
    "Summary:"
)


async def _summarise_one(session: aiohttp.ClientSession,
                         title: str,
                         abstract: str,
                         model: str = "llama3.2") -> str:
    """Return a one‑sentence summary, or empty string on failure."""
    prompt = SUMMARY_PROMPT.format(title=title, abstract=abstract or "No abstract.")
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 120         # enough for a full sentence
        }
    }
    for attempt in range(2):
        try:
            async with session.post(OLLAMA_URL, json=payload, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", "").strip()
                elif resp.status == 500 and attempt < 1:
                    await asyncio.sleep(3)    # retry once after a short wait
                    continue
        except Exception:
            if attempt < 1:
                await asyncio.sleep(2)
    return ""


async def summarise_papers(papers: List[dict],
                           concurrency: int = 1,
                           model: str = "llama3.2") -> List[dict]:
    """Add an 'ai_summary' field to each paper (in place)."""
    if not papers:
        return papers
    sem = asyncio.Semaphore(concurrency)

    async def _worker(paper):
        async with sem:
            summary = await _summarise_one(
                session, paper.get("title", ""),
                paper.get("abstract", ""), model
            )
            paper["ai_summary"] = summary

    async with aiohttp.ClientSession() as session:
        tasks = [_worker(p) for p in papers]
        await asyncio.gather(*tasks)
    return papers