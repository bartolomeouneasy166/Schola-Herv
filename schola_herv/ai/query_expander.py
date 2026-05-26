"""
LLM query expansion using Ollama.
Takes a list of keywords and returns a list of refined search queries.
"""

import asyncio
import aiohttp
from typing import List

import os
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")


async def expand_query(keywords: List[str],
                       model: str = "llama3.2",
                       num_queries: int = 20,
                       max_retries: int = 2) -> List[str]:
    """
    Call Ollama to generate diverse search queries for the given topics.
    Returns a list of query strings (or original keywords on failure).
    """
    topic_text = ", ".join(keywords)
    # Short, structured prompt – less likely to cause 500
    prompt = (
        f"Generate {num_queries} diverse search queries for: {topic_text}.\n"
        f"Use double quotes around phrases.\n"
        f"One query per line, no extra text.\n"
        f"Queries:"
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 400,  # smaller output size
            "stop": ["\n\n"]      # stop at blank line
        }
    }

    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries + 1):
            try:
                async with session.post(OLLAMA_URL, json=payload, timeout=60) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response_text = data.get("response", "")
                        # Parse lines
                        queries = []
                        for line in response_text.strip().splitlines():
                            line = line.strip()
                            if line:
                                queries.append(line)
                        if queries:
                            return queries[:num_queries]  # cap to requested number
                        else:
                            # If empty, retry or fall back
                            continue
                    elif resp.status == 500:
                        # Wait and retry
                        if attempt < max_retries:
                            await asyncio.sleep(3)
                            continue
            except Exception as e:
                if attempt < max_retries:
                    await asyncio.sleep(2)
                continue

    # Fallback: return original keywords
    print(f"Warning: Query expansion failed after {max_retries+1} attempts, using original keywords.")
    return keywords