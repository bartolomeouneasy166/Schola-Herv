"""
LLM-based relevance screening using Ollama.
Scores papers by reading title + abstract, keeps only those ≥ threshold.
"""

import asyncio
from typing import List, Optional

import aiohttp

import os
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")

RATING_PROMPT = """You are a research assistant helping to build a high-quality academic corpus.
Read the paper title and abstract below.
Rate how relevant it is to the research topic: "{topic}".
Use a scale from 1 (not relevant) to 5 (exactly on topic).
Respond with only a single integer number (1-5), no other text.

Title: {title}
Abstract: {abstract}
Relevance (1-5):"""


async def score_paper(session: aiohttp.ClientSession,
                      title: str,
                      abstract: str,
                      topic: str,
                      model: str = "llama3.2",
                      semaphore: asyncio.Semaphore = None) -> int:
    """Score a single paper's relevance. Returns 3 (neutral) on any error."""
    prompt = RATING_PROMPT.format(topic=topic, title=title, abstract=abstract or "No abstract available.")
    
    async def _call():
        try:
            async with session.post(
                OLLAMA_URL,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 5}
                },
                timeout=30
            ) as resp:
                if resp.status != 200:
                    return 3   # neutral fallback
                data = await resp.json()
                response = data.get("response", "").strip()
                # extract first digit
                for char in response:
                    if char.isdigit():
                        score = int(char)
                        return min(max(score, 1), 5)   # clamp 1-5
                return 3
        except Exception:
            return 3

    if semaphore:
        async with semaphore:
            return await _call()
    return await _call()


async def filter_by_relevance(papers: List[dict],
                              topic: str,
                              threshold: int = 4,
                              concurrency: int = 5,
                              model: str = "llama3.2") -> List[dict]:
    """
    Score all papers, keep only those with relevance >= threshold.
    Uses concurrency to speed up multiple Ollama calls.
    """
    if not papers:
        return []
    if threshold <= 1:
        return papers   # no filtering needed

    semaphore = asyncio.Semaphore(concurrency)
    scored_papers = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        for paper in papers:
            title = paper.get("title", "")
            abstract = paper.get("abstract", "")
            task = asyncio.ensure_future(
                score_paper(session, title, abstract, topic, model, semaphore)
            )
            tasks.append(task)

        scores = await asyncio.gather(*tasks)

    filtered = []
    for paper, score in zip(papers, scores):
        paper["relevance_score"] = score
        if score >= threshold:
            filtered.append(paper)

    return filtered