"""
Natural Language → CLI translator using Ollama.
Converts plain English requests into structured JSON that can be fed to the harvester.
"""

import json
import aiohttp
from typing import Optional, Dict

import os
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")

TRANSLATION_PROMPT = """You are an assistant that converts natural language research requests into structured JSON for an academic paper downloader tool called Schola-Herv.

The tool supports these options:
- keywords (list of strings): search terms, comma separated
- sources (string): "arxiv", "crossref", "openalex", "core", "both", "all" (default "all")
- max_results (integer): max papers to download (default 100)
- year_from (integer or null): earliest publication year
- year_to (integer or null): latest publication year
- min_citations (integer or null): minimum citation count
- max_dwn_cites (integer or null): keep only top N most cited papers
- skip_words (list of strings or null): skip papers containing these words in title/abstract
- ai_relevance (integer 1-5 or null): use LLM to score relevance, keep only papers scoring >= this threshold
- ai_summarise (boolean): generate one-sentence summaries for downloaded papers
- ai_expand (boolean): use LLM to expand keywords into diverse queries
- output_dir (string or null): directory to save output

Given a user request, output ONLY a valid JSON object with the appropriate fields. Do NOT include any other text, comments, or code blocks. Only JSON.

Example:
User: "Download 200 recent papers on high energy physics from arxiv, skip surveys"
Output: {{"keywords": ["high energy physics"], "sources": "arxiv", "max_results": 200, "skip_words": ["survey"], "year_from": null, "year_to": null, "min_citations": null, "max_dwn_cites": null, "ai_relevance": null, "ai_summarise": false, "ai_expand": false, "output_dir": null}}

User: "Get 5000 papers on quantum computing from 2020 onwards, only highly cited ones, and expand the search"
Output: {{"keywords": ["quantum computing"], "sources": "all", "max_results": 5000, "year_from": 2020, "max_dwn_cites": 5000, "ai_expand": true, "ai_relevance": null, "ai_summarise": false, "output_dir": null}}

User: "Deep learning papers from nature or ieee, only the most relevant 100, with AI summaries"
Output: {{"keywords": ["deep learning"], "sources": "crossref", "max_results": 100, "ai_relevance": 4, "ai_summarise": true, "year_from": null, "year_to": null, "min_citations": null, "max_dwn_cites": null, "skip_words": null, "ai_expand": false, "output_dir": null}}

Now convert this request:
"{input}"
Output:"""


async def translate_natural_language(query: str, model: str = "llama3.2") -> Optional[Dict]:
    """
    Send a natural language query to Ollama and return a dictionary
    of CLI arguments, or None on failure.
    """
    prompt = TRANSLATION_PROMPT.format(input=query)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 300}
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(OLLAMA_URL, json=payload, timeout=60) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                response_text = data.get("response", "").strip()
                # Try to extract JSON from the response (in case model adds extra text)
                start = response_text.find('{')
                end = response_text.rfind('}')
                if start != -1 and end != -1:
                    json_str = response_text[start:end+1]
                    parsed = json.loads(json_str)
                    # Ensure keywords is a list
                    if isinstance(parsed.get("keywords"), str):
                        parsed["keywords"] = [k.strip() for k in parsed["keywords"].split(",") if k.strip()]
                    return parsed
                return None
        except Exception:
            return None