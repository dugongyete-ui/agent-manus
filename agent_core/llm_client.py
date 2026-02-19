"""LLM Client - Menghubungkan agen ke API AI dengan multi-model support, retry logic, dan validasi data."""

import asyncio
import json
import logging
import re
import time
import random
from typing import Optional, AsyncIterator

import aiohttp

logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://22f0ee02-5482-4584-a7aa-bb5f61e50c6b-00-iq4otn6awuiy.janeway.replit.dev"
DEFAULT_PROVIDER = "Perplexity"
DEFAULT_MODEL = "claude40opusthinking_labs"

AVAILABLE_MODELS = {
    "gpt5_thinking": {
        "name": "GPT-5 Thinking",
        "provider": "Perplexity",
        "category": "thinking",
        "description": "OpenAI GPT-5 dengan kemampuan reasoning mendalam",
    },
    "03": {
        "name": "O3",
        "provider": "Perplexity",
        "category": "reasoning",
        "description": "OpenAI O3 reasoning model",
    },
    "o3pro": {
        "name": "O3 Pro",
        "provider": "Perplexity",
        "category": "reasoning",
        "description": "OpenAI O3 Pro - reasoning lanjutan",
    },
    "claude40opus": {
        "name": "Claude 4.0 Opus",
        "provider": "Perplexity",
        "category": "general",
        "description": "Anthropic Claude 4.0 Opus",
    },
    "claude40opusthinking": {
        "name": "Claude 4.0 Opus Thinking",
        "provider": "Perplexity",
        "category": "thinking",
        "description": "Claude 4.0 Opus dengan mode thinking",
    },
    "claude41opusthinking": {
        "name": "Claude 4.1 Opus Thinking",
        "provider": "Perplexity",
        "category": "thinking",
        "description": "Claude 4.1 Opus dengan mode thinking terbaru",
    },
    "claude45sonnet": {
        "name": "Claude 4.5 Sonnet",
        "provider": "Perplexity",
        "category": "general",
        "description": "Claude 4.5 Sonnet - cepat dan efisien",
    },
    "claude45sonnetthinking": {
        "name": "Claude 4.5 Sonnet Thinking",
        "provider": "Perplexity",
        "category": "thinking",
        "description": "Claude 4.5 Sonnet dengan mode thinking",
    },
    "grok4": {
        "name": "Grok 4",
        "provider": "Perplexity",
        "category": "general",
        "description": "xAI Grok 4",
    },
    "o3_research": {
        "name": "O3 Research",
        "provider": "Perplexity",
        "category": "research",
        "description": "OpenAI O3 optimized untuk riset",
    },
    "o3pro_research": {
        "name": "O3 Pro Research",
        "provider": "Perplexity",
        "category": "research",
        "description": "OpenAI O3 Pro optimized untuk riset mendalam",
    },
    "claude40sonnetthinking_research": {
        "name": "Claude 4.0 Sonnet Thinking Research",
        "provider": "Perplexity",
        "category": "research",
        "description": "Claude 4.0 Sonnet Thinking untuk riset",
    },
    "o3pro_labs": {
        "name": "O3 Pro Labs",
        "provider": "Perplexity",
        "category": "labs",
        "description": "OpenAI O3 Pro edisi labs/eksperimental",
    },
    "claude40opusthinking_labs": {
        "name": "Claude 4.0 Opus Thinking Labs",
        "provider": "Perplexity",
        "category": "labs",
        "description": "Claude 4.0 Opus Thinking edisi labs",
    },
    "r1": {
        "name": "R1",
        "provider": "Perplexity",
        "category": "reasoning",
        "description": "DeepSeek R1 reasoning model",
    },
}

MODEL_CATEGORIES = {
    "thinking": "Model dengan kemampuan reasoning/thinking mendalam",
    "reasoning": "Model optimized untuk penalaran logis",
    "general": "Model serbaguna untuk berbagai tugas",
    "research": "Model optimized untuk riset dan analisis",
    "labs": "Model eksperimental/labs terbaru",
}

RETRY_CONFIG = {
    "max_retries": 5,
    "base_delay": 1.0,
    "max_delay": 30.0,
    "backoff_factor": 2.0,
    "jitter": True,
    "retryable_status_codes": {429, 500, 502, 503, 504},
}

DANGEROUS_PATTERNS = [
    re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
    re.compile(r'javascript:', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),
    re.compile(r'eval\s*\(', re.IGNORECASE),
    re.compile(r'__import__\s*\(', re.IGNORECASE),
    re.compile(r'exec\s*\(', re.IGNORECASE),
    re.compile(r'subprocess', re.IGNORECASE),
    re.compile(r'os\.system', re.IGNORECASE),
]


def sanitize_response(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    cleaned = text
    for pattern in DANGEROUS_PATTERNS:
        cleaned = pattern.sub('[FILTERED]', cleaned)
    return cleaned


def validate_json_response(data) -> dict:
    if data is None:
        return {"valid": False, "error": "Data kosong", "data": None}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return {"valid": True, "data": data, "type": "text"}
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if isinstance(v, str):
                sanitized[k] = sanitize_response(v)
            elif isinstance(v, (dict, list)):
                sanitized[k] = v
            else:
                sanitized[k] = v
        return {"valid": True, "data": sanitized, "type": "dict"}
    if isinstance(data, list):
        return {"valid": True, "data": data, "type": "list"}
    return {"valid": True, "data": data, "type": type(data).__name__}


def generate_query_params(user_intent: str) -> dict:
    intent_lower = user_intent.lower()
    params = {"text": user_intent}
    if any(w in intent_lower for w in ["cari", "search", "find", "temukan"]):
        params["mode"] = "search"
    elif any(w in intent_lower for w in ["analisis", "analyze", "review"]):
        params["mode"] = "analysis"
    elif any(w in intent_lower for w in ["tulis", "write", "buat", "create", "generate"]):
        params["mode"] = "generation"
    elif any(w in intent_lower for w in ["jelaskan", "explain", "apa itu", "what is"]):
        params["mode"] = "explanation"
    elif any(w in intent_lower for w in ["terjemahkan", "translate"]):
        params["mode"] = "translation"
    elif any(w in intent_lower for w in ["ringkas", "summarize", "summary"]):
        params["mode"] = "summarization"
    elif any(w in intent_lower for w in ["kode", "code", "program", "script"]):
        params["mode"] = "coding"
    else:
        params["mode"] = "general"
    return params


class LLMClient:
    def __init__(
        self,
        api_base: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 120,
    ):
        self.api_base = (api_base or DEFAULT_API_BASE).rstrip("/")
        self.provider = provider or DEFAULT_PROVIDER
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout
        self.stream_url = f"{self.api_base}/stream"
        self._session: Optional[aiohttp.ClientSession] = None
        self._retry_stats = {
            "total_requests": 0,
            "total_retries": 0,
            "total_failures": 0,
            "last_error": None,
            "model_errors": {},
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    def set_model(self, model: str) -> bool:
        if model in AVAILABLE_MODELS:
            self.model = model
            self.provider = AVAILABLE_MODELS[model]["provider"]
            logger.info(f"Model diubah ke: {model} (provider: {self.provider})")
            return True
        logger.warning(f"Model tidak dikenal: {model}")
        return False

    def get_current_model(self) -> dict:
        model_info = AVAILABLE_MODELS.get(self.model, {})
        return {
            "model": self.model,
            "provider": self.provider,
            "name": model_info.get("name", self.model),
            "category": model_info.get("category", "unknown"),
            "description": model_info.get("description", ""),
        }

    @staticmethod
    def list_models(category: Optional[str] = None) -> list[dict]:
        models = []
        for model_id, info in AVAILABLE_MODELS.items():
            if category and info.get("category") != category:
                continue
            models.append({
                "id": model_id,
                "name": info["name"],
                "provider": info["provider"],
                "category": info["category"],
                "description": info["description"],
            })
        return models

    @staticmethod
    def list_categories() -> dict:
        return MODEL_CATEGORIES.copy()

    def _calculate_retry_delay(self, attempt: int) -> float:
        delay = min(
            RETRY_CONFIG["base_delay"] * (RETRY_CONFIG["backoff_factor"] ** attempt),
            RETRY_CONFIG["max_delay"],
        )
        if RETRY_CONFIG["jitter"]:
            delay = delay * (0.5 + random.random() * 0.5)
        return delay

    async def _request_with_retry(
        self, session: aiohttp.ClientSession, payload: dict
    ) -> aiohttp.ClientResponse:
        self._retry_stats["total_requests"] += 1
        last_exception = None

        for attempt in range(RETRY_CONFIG["max_retries"] + 1):
            try:
                resp = await session.post(
                    self.stream_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status == 200:
                    return resp

                if resp.status in RETRY_CONFIG["retryable_status_codes"]:
                    error_text = await resp.text()
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            delay = self._calculate_retry_delay(attempt)
                    else:
                        delay = self._calculate_retry_delay(attempt)

                    self._retry_stats["total_retries"] += 1
                    logger.warning(
                        f"API {resp.status} (attempt {attempt+1}/{RETRY_CONFIG['max_retries']+1}), "
                        f"retry in {delay:.1f}s: {error_text[:100]}"
                    )
                    await resp.release()
                    await asyncio.sleep(delay)
                    continue
                else:
                    return resp

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < RETRY_CONFIG["max_retries"]:
                    delay = self._calculate_retry_delay(attempt)
                    self._retry_stats["total_retries"] += 1
                    logger.warning(
                        f"Connection error (attempt {attempt+1}), retry in {delay:.1f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    self._retry_stats["total_failures"] += 1
                    self._retry_stats["last_error"] = str(e)
                    raise

        self._retry_stats["total_failures"] += 1
        if last_exception:
            raise last_exception
        raise aiohttp.ClientError("Max retries exceeded")

    async def chat(self, text: str) -> str:
        full_response = []
        async for chunk in self.chat_stream(text):
            full_response.append(chunk)
        return "".join(full_response)

    async def chat_stream(self, text: str) -> AsyncIterator[str]:
        session = await self._get_session()
        query_params = generate_query_params(text)
        payload = {
            "text": text,
            "provider": self.provider,
            "model": self.model,
        }

        logger.debug(f"LLM request ke {self.stream_url} [model={self.model}]: {text[:100]}...")

        try:
            resp = await self._request_with_retry(session, payload)

            if resp.status != 200:
                error_text = await resp.text()
                logger.error(f"API error {resp.status}: {error_text[:200]}")
                model_key = self.model
                self._retry_stats["model_errors"][model_key] = (
                    self._retry_stats["model_errors"].get(model_key, 0) + 1
                )
                yield f"[Error API: {resp.status}]"
                return

            async for line in resp.content:
                decoded = line.decode("utf-8", errors="replace").strip()
                if not decoded:
                    continue

                if decoded.startswith("data: "):
                    data_part = decoded[6:]

                    if data_part == "[DONE]":
                        break

                    try:
                        parsed = json.loads(data_part)
                        validated = validate_json_response(parsed)
                        if validated["valid"]:
                            if validated["type"] == "text" or isinstance(validated["data"], str):
                                sanitized = sanitize_response(str(validated["data"]))
                                yield sanitized
                            elif isinstance(validated["data"], dict):
                                content = validated["data"].get("content") or validated["data"].get("text") or validated["data"].get("message")
                                if content:
                                    yield sanitize_response(str(content))
                                else:
                                    yield sanitize_response(json.dumps(validated["data"], ensure_ascii=False))
                            else:
                                yield sanitize_response(str(validated["data"]))
                        else:
                            logger.warning(f"Invalid response data: {validated.get('error')}")
                    except json.JSONDecodeError:
                        sanitized = sanitize_response(data_part)
                        yield sanitized

        except asyncio.TimeoutError:
            logger.error("LLM request timeout")
            yield "[Error: Request timeout]"
        except aiohttp.ClientError as e:
            logger.error(f"LLM connection error: {e}")
            yield f"[Error koneksi: {e}]"
        except Exception as e:
            logger.error(f"LLM unexpected error: {e}")
            yield f"[Error: {e}]"

    async def chat_with_system(self, system_prompt: str, user_message: str) -> str:
        combined = f"{system_prompt}\n\nUser: {user_message}"
        return await self.chat(combined)

    async def chat_with_context(self, messages: list[dict]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System]: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        combined = "\n\n".join(parts)
        return await self.chat(combined)

    def get_retry_stats(self) -> dict:
        return self._retry_stats.copy()

    def reset_retry_stats(self):
        self._retry_stats = {
            "total_requests": 0,
            "total_retries": 0,
            "total_failures": 0,
            "last_error": None,
            "model_errors": {},
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def __del__(self):
        if self._session and not self._session.closed:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.close())
                else:
                    loop.run_until_complete(self.close())
            except Exception:
                pass
