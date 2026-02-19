"""Search Tool - Pencarian web menggunakan HTTP request dan scraping."""

import asyncio
import json
import logging
import re
import time
import urllib.parse
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

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
    USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(self, max_results: int = 10, cache_ttl: int = 3600, timeout: int = 15):
        self.max_results = max_results
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self.cache: dict[str, dict] = {}
        self.search_history: list[dict] = []
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={"User-Agent": self.USER_AGENT},
            )
        return self._session

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

        results = await self._search_duckduckgo_html(query, max_results)

        if not results:
            results = await self._search_duckduckgo_lite(query, max_results)

        if not results:
            logger.warning(f"Tidak ada hasil ditemukan untuk: '{query}'")

        self._cache_results(query, results)
        self.search_history.append({"query": query, "results_count": len(results), "timestamp": time.time()})

        return results

    async def _search_duckduckgo_html(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            session = await self._get_session()
            encoded_query = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"DuckDuckGo HTML status: {resp.status}")
                    return []
                html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")
            results = []

            for result_div in soup.select(".result"):
                title_el = result_div.select_one(".result__title a, .result__a")
                snippet_el = result_div.select_one(".result__snippet")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                href = str(title_el.get("href", ""))

                if "duckduckgo.com/y.js" in href or "uddg=" in href:
                    match = re.search(r'uddg=([^&]+)', href)
                    if match:
                        href = urllib.parse.unquote(match.group(1))

                if not href or not href.startswith("http"):
                    continue

                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                results.append(SearchResult(title=title, url=href, snippet=snippet, source="duckduckgo"))

                if len(results) >= max_results:
                    break

            logger.info(f"DuckDuckGo HTML: {len(results)} hasil untuk '{query}'")
            return results

        except Exception as e:
            logger.error(f"Error DuckDuckGo HTML search: {e}")
            return []

    async def _search_duckduckgo_lite(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            session = await self._get_session()
            url = "https://lite.duckduckgo.com/lite/"
            data = {"q": query}

            async with session.post(url, data=data) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")
            results = []

            for link in soup.select("a.result-link"):
                title = link.get_text(strip=True)
                href = str(link.get("href", ""))
                if href and href.startswith("http"):
                    snippet_td = link.find_parent("tr")
                    snippet = ""
                    if snippet_td:
                        next_tr = snippet_td.find_next_sibling("tr")
                        if next_tr:
                            snippet = next_tr.get_text(strip=True)[:300]
                    results.append(SearchResult(title=title, url=href, snippet=snippet, source="duckduckgo_lite"))
                    if len(results) >= max_results:
                        break

            logger.info(f"DuckDuckGo Lite: {len(results)} hasil untuk '{query}'")
            return results

        except Exception as e:
            logger.error(f"Error DuckDuckGo Lite search: {e}")
            return []

    async def fetch_page_content(self, url: str, max_length: int = 50000) -> dict:
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    return {"success": False, "error": f"HTTP {resp.status}"}
                html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")

            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            text = soup.get_text(separator="\n", strip=True)

            lines = [line.strip() for line in text.splitlines() if line.strip()]
            clean_text = "\n".join(lines)[:max_length]

            return {
                "success": True,
                "url": url,
                "title": title,
                "text": clean_text,
                "text_length": len(clean_text),
            }

        except Exception as e:
            return {"success": False, "url": url, "error": str(e)}

    async def multi_search(self, queries: list[str], max_results_per_query: int = 5) -> dict:
        all_results = {}
        for query in queries:
            results = await self.search(query, max_results=max_results_per_query)
            all_results[query] = [r.to_dict() for r in results]
        return all_results

    def _extract_query(self, text: str) -> str:
        prefixes = ["cari ", "temukan ", "search ", "find ", "google "]
        text_lower = text.lower()
        for prefix in prefixes:
            if text_lower.startswith(prefix):
                return text[len(prefix):].strip()
        return text.strip()

    def _format_results(self, results: list[SearchResult]) -> str:
        if not results:
            return "Tidak ada hasil ditemukan."
        lines = []
        for i, result in enumerate(results, 1):
            lines.append(f"{i}. **{result.title}**")
            lines.append(f"   URL: {result.url}")
            if result.snippet:
                lines.append(f"   {result.snippet[:300]}")
            lines.append("")
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

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
