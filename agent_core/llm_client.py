"""LLM Client - Menghubungkan agen ke API Dzeck AI untuk pemrosesan bahasa alami."""

import asyncio
import json
import logging
from typing import Optional, AsyncIterator

import aiohttp

logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://22f0ee02-5482-4584-a7aa-bb5f61e50c6b-00-iq4otn6awuiy.janeway.replit.dev"
DEFAULT_PROVIDER = "Perplexity"
DEFAULT_MODEL = "claude40opusthinking_labs"


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

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    async def chat(self, text: str) -> str:
        full_response = []
        async for chunk in self.chat_stream(text):
            full_response.append(chunk)
        return "".join(full_response)

    async def chat_stream(self, text: str) -> AsyncIterator[str]:
        session = await self._get_session()
        payload = {
            "text": text,
            "provider": self.provider,
            "model": self.model,
        }

        logger.debug(f"LLM request ke {self.stream_url}: {text[:100]}...")

        try:
            async with session.post(
                self.stream_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"API error {resp.status}: {error_text[:200]}")
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
                            text_chunk = json.loads(data_part)
                            if isinstance(text_chunk, str):
                                yield text_chunk
                        except json.JSONDecodeError:
                            yield data_part

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
