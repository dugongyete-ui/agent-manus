"""Search Tool - Wrapper untuk API pencarian eksternal."""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class SearchResult:
    def __init__(self, title: str, url: str, snippet: str, source: str = "web"):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.source = source
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
        }


class SearchTool:
    def __init__(self, max_results: int = 10, cache_ttl: int = 3600):
        self.max_results = max_results
        self.cache_ttl = cache_ttl
        self.cache: dict[str, dict] = {}
        self.search_history: list[dict] = []

    async def execute(self, plan: dict) -> str:
        intent = plan.get("intent", "")
        input_text = plan.get("analysis", {}).get("input", "")
        query = self._extract_query(input_text)
        if query:
            results = await self.search(query)
            if results:
                formatted = self._format_results(results)
                return f"Hasil pencarian untuk '{query}':\n{formatted}"
        return f"Search tool siap. Intent: {intent}. Gunakan metode search() untuk mencari."

    async def search(self, query: str, max_results: Optional[int] = None) -> list[SearchResult]:
        max_results = max_results or self.max_results
        logger.info(f"Pencarian: '{query}' (maks: {max_results})")

        cached = self._get_cached(query)
        if cached:
            logger.info(f"Hasil dari cache untuk: '{query}'")
            return cached

        results = self._simulate_search(query, max_results)

        self._cache_results(query, results)
        self.search_history.append({"query": query, "results_count": len(results), "timestamp": time.time()})

        return results

    def _simulate_search(self, query: str, max_results: int) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"Hasil pencarian untuk: {query}",
                url=f"https://example.com/search?q={query.replace(' ', '+')}",
                snippet=f"Informasi terkait '{query}' ditemukan dari sumber terpercaya.",
                source="web",
            )
        ]

    def _extract_query(self, text: str) -> str:
        prefixes = ["cari ", "temukan ", "search ", "find "]
        text_lower = text.lower()
        for prefix in prefixes:
            if text_lower.startswith(prefix):
                return text[len(prefix):].strip()
        return text.strip()

    def _format_results(self, results: list[SearchResult]) -> str:
        lines = []
        for i, result in enumerate(results, 1):
            lines.append(f"{i}. [{result.title}]({result.url})")
            lines.append(f"   {result.snippet}")
        return "\n".join(lines)

    def _get_cached(self, query: str) -> Optional[list[SearchResult]]:
        key = query.lower().strip()
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry["timestamp"] < self.cache_ttl:
                return entry["results"]
            del self.cache[key]
        return None

    def _cache_results(self, query: str, results: list[SearchResult]):
        key = query.lower().strip()
        self.cache[key] = {"results": results, "timestamp": time.time()}

    def get_search_history(self) -> list[dict]:
        return self.search_history
