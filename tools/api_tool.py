"""API Tool - Integrasi REST API dengan rate limiting, caching, dan timeout handling."""

import asyncio
import json
import logging
import time
import xml.etree.ElementTree as ET
from typing import Optional
from collections import defaultdict

import aiohttp

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
MAX_RESPONSE_SIZE = 5 * 1024 * 1024
CACHE_TTL = 300
MAX_CACHE_ENTRIES = 200

BLOCKED_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "metadata.google.internal", "169.254.169.254",
}

ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


class ApiTool:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT, rate_limit_per_host: int = 30, cache_ttl: int = CACHE_TTL):
        self.timeout = timeout
        self.rate_limit_per_host = rate_limit_per_host
        self.cache_ttl = cache_ttl
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: dict[str, dict] = {}
        self._rate_limits: dict[str, list[float]] = defaultdict(list)
        self.request_history: list[dict] = []

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={
                    "User-Agent": "ManusAgent-ApiTool/1.0",
                    "Accept": "application/json, text/plain, */*",
                },
            )
        return self._session

    async def execute(self, params: dict) -> str:
        action = params.get("action", "")

        try:
            if action == "request":
                return await self._make_request(params)
            else:
                return (
                    "API tool siap. Aksi tersedia: request.\n"
                    "Contoh: {\"action\": \"request\", \"method\": \"GET\", \"url\": \"https://api.example.com/data\"}\n"
                    "Parameter opsional: headers, body, params, auth_token, timeout, cache"
                )
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error: {e}")
            return f"Error HTTP: {e}"
        except asyncio.TimeoutError:
            logger.error("Request timeout")
            return f"Error: Request timeout setelah {self.timeout} detik."
        except Exception as e:
            logger.error(f"Error tidak terduga: {e}")
            return f"Error: {e}"

    async def _make_request(self, params: dict) -> str:
        method = params.get("method", "GET").upper()
        url = params.get("url", "").strip()
        headers = params.get("headers", {})
        body = params.get("body")
        query_params = params.get("params", {})
        auth_token = params.get("auth_token", "")
        req_timeout = params.get("timeout", self.timeout)
        use_cache = params.get("cache", method == "GET")

        if not url:
            return "Error: parameter 'url' diperlukan."

        if method not in ALLOWED_METHODS:
            return f"Error: method '{method}' tidak didukung. Gunakan: {', '.join(sorted(ALLOWED_METHODS))}"

        safety_msg = self._check_url_safety(url)
        if safety_msg:
            return safety_msg

        rate_msg = self._check_rate_limit(url)
        if rate_msg:
            return rate_msg

        if use_cache and method == "GET":
            cached = self._get_cached(method, url, query_params)
            if cached:
                logger.info(f"Cache hit: {method} {url}")
                return cached

        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}" if not auth_token.startswith("Bearer ") else auth_token

        logger.info(f"API Request: {method} {url}")

        session = await self._get_session()
        request_kwargs: dict = {
            "method": method,
            "url": url,
            "headers": headers,
            "timeout": aiohttp.ClientTimeout(total=req_timeout),
        }

        if query_params:
            request_kwargs["params"] = query_params

        if body and method in ("POST", "PUT", "PATCH"):
            if isinstance(body, (dict, list)):
                request_kwargs["json"] = body
            elif isinstance(body, str):
                request_kwargs["data"] = body
            else:
                request_kwargs["data"] = str(body)

        start_time = time.time()

        async with session.request(**request_kwargs) as resp:
            duration_ms = int((time.time() - start_time) * 1000)
            status = resp.status
            resp_headers = dict(resp.headers)
            content_type = resp.content_type or ""

            content_length = resp.content_length or 0
            if content_length > MAX_RESPONSE_SIZE:
                return f"Error: respons terlalu besar ({content_length} bytes, maks {MAX_RESPONSE_SIZE} bytes)."

            raw_body = await resp.read()
            if len(raw_body) > MAX_RESPONSE_SIZE:
                return f"Error: respons terlalu besar ({len(raw_body)} bytes, maks {MAX_RESPONSE_SIZE} bytes)."

            body_text = raw_body.decode("utf-8", errors="replace")
            parsed_body = self._parse_response_body(body_text, content_type)

            self.request_history.append({
                "method": method,
                "url": url,
                "status": status,
                "duration_ms": duration_ms,
                "response_size": len(raw_body),
                "timestamp": time.time(),
            })

            result = self._format_response(method, url, status, resp_headers, parsed_body, duration_ms)

            if use_cache and method == "GET" and 200 <= status < 300:
                self._cache_response(method, url, query_params, result)

            return result

    def _check_url_safety(self, url: str) -> Optional[str]:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)

            if parsed.scheme not in ("http", "https"):
                return f"Error: hanya HTTP dan HTTPS yang didukung (ditemukan: '{parsed.scheme}')."

            hostname = parsed.hostname or ""
            if hostname in BLOCKED_HOSTS:
                return f"Error: akses ke host '{hostname}' diblokir untuk keamanan."

            if hostname.startswith("10.") or hostname.startswith("192.168.") or hostname.startswith("172."):
                return f"Error: akses ke jaringan internal ({hostname}) diblokir."

        except Exception:
            return "Error: URL tidak valid."

        return None

    def _check_rate_limit(self, url: str) -> Optional[str]:
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname or "unknown"
        now = time.time()

        self._rate_limits[hostname] = [t for t in self._rate_limits[hostname] if now - t < 60]

        if len(self._rate_limits[hostname]) >= self.rate_limit_per_host:
            return (
                f"Error: rate limit tercapai untuk '{hostname}' "
                f"({self.rate_limit_per_host} request/menit). Coba lagi nanti."
            )

        self._rate_limits[hostname].append(now)
        return None

    def _parse_response_body(self, body: str, content_type: str) -> str:
        body = body.strip()
        if not body:
            return "(respons kosong)"

        if "json" in content_type or body.startswith(("{", "[")):
            try:
                parsed = json.loads(body)
                formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                if len(formatted) > 50000:
                    formatted = formatted[:50000] + "\n... (output terpotong)"
                return formatted
            except (json.JSONDecodeError, ValueError):
                pass

        if "xml" in content_type or body.startswith("<?xml") or body.startswith("<"):
            try:
                root = ET.fromstring(body)
                return self._xml_to_readable(root)
            except ET.ParseError:
                pass

        if len(body) > 50000:
            body = body[:50000] + "\n... (output terpotong)"

        return body

    def _xml_to_readable(self, element: ET.Element, indent: int = 0) -> str:
        lines = []
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        prefix = "  " * indent

        attrs = " ".join(f'{k}="{v}"' for k, v in element.attrib.items())
        header = f"{prefix}<{tag}"
        if attrs:
            header += f" {attrs}"

        text = (element.text or "").strip()
        children = list(element)

        if not children and not text:
            lines.append(f"{header} />")
        elif not children:
            if len(text) > 200:
                text = text[:197] + "..."
            lines.append(f"{header}>{text}</{tag}>")
        else:
            lines.append(f"{header}>")
            if text:
                lines.append(f"{prefix}  {text}")
            for child in children[:50]:
                lines.append(self._xml_to_readable(child, indent + 1))
            if len(children) > 50:
                lines.append(f"{prefix}  ... ({len(children) - 50} elemen lagi)")
            lines.append(f"{prefix}</{tag}>")

        return "\n".join(lines)

    def _format_response(self, method: str, url: str, status: int, headers: dict, body: str, duration_ms: int) -> str:
        status_text = "OK" if 200 <= status < 300 else "Redirect" if 300 <= status < 400 else "Client Error" if 400 <= status < 500 else "Server Error" if status >= 500 else "Unknown"

        lines = [
            f"=== API Response ===",
            f"Request: {method} {url}",
            f"Status: {status} ({status_text})",
            f"Duration: {duration_ms}ms",
            "",
            "--- Headers ---",
        ]

        important_headers = [
            "content-type", "content-length", "x-ratelimit-remaining",
            "x-ratelimit-limit", "retry-after", "location",
            "cache-control", "etag", "last-modified",
        ]
        for key in important_headers:
            val = headers.get(key) or headers.get(key.title()) or headers.get(key.replace("-", "_"))
            if val:
                lines.append(f"  {key}: {val}")

        lines.append("")
        lines.append("--- Body ---")
        lines.append(body)

        return "\n".join(lines)

    def _cache_key(self, method: str, url: str, query_params: dict) -> str:
        param_str = json.dumps(query_params, sort_keys=True) if query_params else ""
        return f"{method}:{url}:{param_str}"

    def _get_cached(self, method: str, url: str, query_params: dict) -> Optional[str]:
        key = self._cache_key(method, url, query_params)
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["timestamp"] < self.cache_ttl:
                return entry["result"] + "\n\n(dari cache)"
            del self._cache[key]
        return None

    def _cache_response(self, method: str, url: str, query_params: dict, result: str):
        if len(self._cache) >= MAX_CACHE_ENTRIES:
            oldest_key = min(self._cache, key=lambda k: self._cache[k]["timestamp"])
            del self._cache[oldest_key]

        key = self._cache_key(method, url, query_params)
        self._cache[key] = {"result": result, "timestamp": time.time()}

    def get_request_history(self, limit: int = 20) -> list[dict]:
        return self.request_history[-limit:]

    def clear_cache(self):
        self._cache.clear()
        logger.info("API cache dibersihkan.")

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
