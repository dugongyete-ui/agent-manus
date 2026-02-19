"""MCP Providers - Adapter untuk berbagai LLM provider dengan interface seragam."""

import asyncio
import json
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

import aiohttp

from mcp.protocol import (
    MCPMessage, MCPRequest, MCPResponse, MCPStreamChunk,
    MCPProviderConfig, MCPProviderType, MCPRole, MCPMessageType,
    MCPStatus, MCPUsage, MCPToolCall, MCPToolDefinition,
)

logger = logging.getLogger(__name__)


class MCPProvider(ABC):
    def __init__(self, config: MCPProviderConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._stats = {
            "total_requests": 0,
            "total_retries": 0,
            "total_failures": 0,
            "total_tokens_used": 0,
            "avg_latency_ms": 0,
            "last_error": None,
        }

    @abstractmethod
    async def complete(self, request: MCPRequest) -> MCPResponse:
        pass

    @abstractmethod
    async def stream(self, request: MCPRequest) -> AsyncIterator[MCPStreamChunk]:
        pass

    @abstractmethod
    def format_messages(self, messages: list[MCPMessage]) -> list[dict]:
        pass

    @abstractmethod
    def format_tools(self, tools: list[MCPToolDefinition]) -> list[dict]:
        pass

    @abstractmethod
    def parse_response(self, raw: dict) -> MCPMessage:
        pass

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            headers.update(self.config.headers)
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                headers=headers,
            )
        return self._session

    def _calculate_retry_delay(self, attempt: int) -> float:
        delay = min(1.0 * (2.0 ** attempt), 30.0)
        return delay * (0.5 + random.random() * 0.5)

    async def _request_with_retry(self, url: str, payload: dict, method: str = "POST") -> dict:
        self._stats["total_requests"] += 1
        session = await self._get_session()

        for attempt in range(self.config.max_retries + 1):
            try:
                start = time.time()
                async with session.request(method, url, json=payload) as resp:
                    duration = int((time.time() - start) * 1000)

                    if resp.status == 200:
                        data = await resp.json()
                        self._update_latency(duration)
                        return data

                    if resp.status in {429, 500, 502, 503, 504}:
                        error_text = await resp.text()
                        retry_after = resp.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after else self._calculate_retry_delay(attempt)
                        self._stats["total_retries"] += 1
                        logger.warning(f"[{self.config.name}] HTTP {resp.status}, retry {attempt+1}/{self.config.max_retries}: {error_text[:100]}")
                        await asyncio.sleep(delay)
                        continue

                    error_text = await resp.text()
                    self._stats["total_failures"] += 1
                    self._stats["last_error"] = f"HTTP {resp.status}: {error_text[:200]}"
                    return {"error": error_text, "status": resp.status}

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < self.config.max_retries:
                    delay = self._calculate_retry_delay(attempt)
                    self._stats["total_retries"] += 1
                    logger.warning(f"[{self.config.name}] Connection error, retry {attempt+1}: {e}")
                    await asyncio.sleep(delay)
                else:
                    self._stats["total_failures"] += 1
                    self._stats["last_error"] = str(e)
                    return {"error": str(e), "status": 0}

        self._stats["total_failures"] += 1
        return {"error": "Max retries exceeded", "status": 0}

    async def _stream_request(self, url: str, payload: dict) -> AsyncIterator[str]:
        session = await self._get_session()
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    yield json.dumps({"error": error, "status": resp.status})
                    return
                async for line in resp.content:
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded:
                        yield decoded
        except Exception as e:
            yield json.dumps({"error": str(e), "status": 0})

    def _update_latency(self, duration_ms: int):
        total = self._stats["total_requests"]
        if total <= 1:
            self._stats["avg_latency_ms"] = duration_ms
        else:
            self._stats["avg_latency_ms"] = int(
                (self._stats["avg_latency_ms"] * (total - 1) + duration_ms) / total
            )

    def get_stats(self) -> dict:
        return {**self._stats, "provider": self.config.name, "type": self.config.provider_type.value}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def health_check(self) -> dict:
        return {
            "provider": self.config.name,
            "type": self.config.provider_type.value,
            "enabled": self.config.enabled,
            "models": self.config.available_models,
            "stats": self.get_stats(),
        }


class OpenAIProvider(MCPProvider):
    def format_messages(self, messages: list[MCPMessage]) -> list[dict]:
        formatted = []
        for msg in messages:
            m = {"role": msg.role.value, "content": msg.content}
            if msg.tool_calls:
                m["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                    for tc in msg.tool_calls
                ]
            if msg.role == MCPRole.TOOL and msg.tool_results:
                for tr in msg.tool_results:
                    formatted.append({"role": "tool", "tool_call_id": tr.call_id, "content": tr.content})
                continue
            formatted.append(m)
        return formatted

    def format_tools(self, tools: list[MCPToolDefinition]) -> list[dict]:
        return [t.to_openai_schema() for t in tools]

    def parse_response(self, raw: dict) -> MCPMessage:
        if "error" in raw:
            return MCPMessage(role=MCPRole.ASSISTANT, content=raw.get("error", ""), message_type=MCPMessageType.ERROR)

        choices = raw.get("choices", [])
        if not choices:
            return MCPMessage(role=MCPRole.ASSISTANT, content="Empty response", message_type=MCPMessageType.ERROR)

        choice = choices[0]
        msg_data = choice.get("message", {})
        content = msg_data.get("content", "") or ""
        tool_calls = []

        if "tool_calls" in msg_data:
            for tc in msg_data["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(MCPToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args))

        msg_type = MCPMessageType.TOOL_CALL if tool_calls else MCPMessageType.TEXT
        return MCPMessage(role=MCPRole.ASSISTANT, content=content, message_type=msg_type, tool_calls=tool_calls)

    async def complete(self, request: MCPRequest) -> MCPResponse:
        start = time.time()
        url = f"{self.config.api_base}/chat/completions"
        payload = {
            "model": request.model or self.config.default_model,
            "messages": self.format_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            payload["tools"] = self.format_tools(request.tools)
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences

        raw = await self._request_with_retry(url, payload)
        duration = int((time.time() - start) * 1000)

        if "error" in raw and "choices" not in raw:
            return MCPResponse(
                status=MCPStatus.ERROR, error=str(raw.get("error", "")),
                model=request.model, provider=self.config.name,
                duration_ms=duration, request_id=request.request_id,
            )

        message = self.parse_response(raw)
        usage_data = raw.get("usage", {})
        usage = MCPUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        self._stats["total_tokens_used"] += usage.total_tokens

        return MCPResponse(
            message=message, status=MCPStatus.OK, usage=usage,
            model=request.model or self.config.default_model,
            provider=self.config.name, duration_ms=duration,
            request_id=request.request_id,
        )

    async def stream(self, request: MCPRequest) -> AsyncIterator[MCPStreamChunk]:
        url = f"{self.config.api_base}/chat/completions"
        payload = {
            "model": request.model or self.config.default_model,
            "messages": self.format_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        if request.tools:
            payload["tools"] = self.format_tools(request.tools)

        async for line in self._stream_request(url, payload):
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                yield MCPStreamChunk(finish_reason="stop")
                return
            try:
                data = json.loads(data_str)
                if "error" in data:
                    yield MCPStreamChunk(content=str(data["error"]), delta_type="error")
                    return
                delta = data.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield MCPStreamChunk(content=content, delta_type="text")
                if "tool_calls" in delta:
                    for tc_delta in delta["tool_calls"]:
                        fn = tc_delta.get("function", {})
                        yield MCPStreamChunk(
                            delta_type="tool_call",
                            tool_call=MCPToolCall(
                                id=tc_delta.get("id", ""),
                                name=fn.get("name", ""),
                                arguments=fn.get("arguments", {}),
                            ),
                        )
                finish = data.get("choices", [{}])[0].get("finish_reason")
                if finish:
                    yield MCPStreamChunk(finish_reason=finish)
                    return
            except json.JSONDecodeError:
                continue


class AnthropicProvider(MCPProvider):
    def format_messages(self, messages: list[MCPMessage]) -> list[dict]:
        formatted = []
        system_parts = []
        for msg in messages:
            if msg.role == MCPRole.SYSTEM:
                system_parts.append(msg.content)
                continue
            m = {"role": msg.role.value, "content": msg.content}
            if msg.tool_calls:
                content_blocks = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content_blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
                m["content"] = content_blocks
            if msg.role == MCPRole.TOOL and msg.tool_results:
                content_blocks = []
                for tr in msg.tool_results:
                    content_blocks.append({"type": "tool_result", "tool_use_id": tr.call_id, "content": tr.content})
                m = {"role": "user", "content": content_blocks}
            formatted.append(m)
        return formatted, "\n\n".join(system_parts) if system_parts else ""

    def format_tools(self, tools: list[MCPToolDefinition]) -> list[dict]:
        return [t.to_anthropic_schema() for t in tools]

    def parse_response(self, raw: dict) -> MCPMessage:
        if "error" in raw:
            error_msg = raw.get("error", {})
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("message", str(error_msg))
            return MCPMessage(role=MCPRole.ASSISTANT, content=str(error_msg), message_type=MCPMessageType.ERROR)

        content_blocks = raw.get("content", [])
        text_parts = []
        tool_calls = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(MCPToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=block.get("input", {}),
                ))

        content = "\n".join(text_parts)
        msg_type = MCPMessageType.TOOL_CALL if tool_calls else MCPMessageType.TEXT
        return MCPMessage(role=MCPRole.ASSISTANT, content=content, message_type=msg_type, tool_calls=tool_calls)

    async def complete(self, request: MCPRequest) -> MCPResponse:
        start = time.time()
        url = f"{self.config.api_base}/messages"
        messages_formatted, system_text = self.format_messages(request.messages)

        payload = {
            "model": request.model or self.config.default_model,
            "messages": messages_formatted,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system_text:
            payload["system"] = system_text
        if request.tools:
            payload["tools"] = self.format_tools(request.tools)
        if request.stop_sequences:
            payload["stop_sequences"] = request.stop_sequences

        raw = await self._request_with_retry(url, payload)
        duration = int((time.time() - start) * 1000)

        if "error" in raw and "content" not in raw:
            return MCPResponse(
                status=MCPStatus.ERROR, error=str(raw.get("error", "")),
                model=request.model, provider=self.config.name,
                duration_ms=duration, request_id=request.request_id,
            )

        message = self.parse_response(raw)
        usage_data = raw.get("usage", {})
        usage = MCPUsage(
            prompt_tokens=usage_data.get("input_tokens", 0),
            completion_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
        )
        self._stats["total_tokens_used"] += usage.total_tokens

        return MCPResponse(
            message=message, status=MCPStatus.OK, usage=usage,
            model=raw.get("model", request.model or self.config.default_model),
            provider=self.config.name, duration_ms=duration,
            request_id=request.request_id,
        )

    async def stream(self, request: MCPRequest) -> AsyncIterator[MCPStreamChunk]:
        url = f"{self.config.api_base}/messages"
        messages_formatted, system_text = self.format_messages(request.messages)
        payload = {
            "model": request.model or self.config.default_model,
            "messages": messages_formatted,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }
        if system_text:
            payload["system"] = system_text
        if request.tools:
            payload["tools"] = self.format_tools(request.tools)

        async for line in self._stream_request(url, payload):
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            try:
                data = json.loads(data_str)
                event_type = data.get("type", "")

                if event_type == "content_block_delta":
                    delta = data.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield MCPStreamChunk(content=delta.get("text", ""), delta_type="text")
                    elif delta.get("type") == "input_json_delta":
                        yield MCPStreamChunk(content=delta.get("partial_json", ""), delta_type="tool_input")
                elif event_type == "content_block_start":
                    block = data.get("content_block", {})
                    if block.get("type") == "tool_use":
                        yield MCPStreamChunk(
                            delta_type="tool_call",
                            tool_call=MCPToolCall(id=block.get("id", ""), name=block.get("name", "")),
                        )
                elif event_type == "message_stop":
                    yield MCPStreamChunk(finish_reason="stop")
                    return
                elif event_type == "message_delta":
                    stop = data.get("delta", {}).get("stop_reason")
                    if stop:
                        usage_data = data.get("usage", {})
                        yield MCPStreamChunk(
                            finish_reason=stop,
                            usage=MCPUsage(
                                completion_tokens=usage_data.get("output_tokens", 0),
                                total_tokens=usage_data.get("output_tokens", 0),
                            ) if usage_data else None,
                        )
            except json.JSONDecodeError:
                continue


class GoogleProvider(MCPProvider):
    def format_messages(self, messages: list[MCPMessage]) -> list[dict]:
        formatted = []
        system_instruction = ""
        for msg in messages:
            if msg.role == MCPRole.SYSTEM:
                system_instruction += msg.content + "\n"
                continue
            role = "user" if msg.role == MCPRole.USER else "model"
            parts = [{"text": msg.content}] if msg.content else []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    parts.append({"functionCall": {"name": tc.name, "args": tc.arguments}})
            if msg.tool_results:
                for tr in msg.tool_results:
                    parts.append({"functionResponse": {"name": tr.name, "response": {"content": tr.content}}})
            formatted.append({"role": role, "parts": parts})
        return formatted, system_instruction.strip()

    def format_tools(self, tools: list[MCPToolDefinition]) -> list[dict]:
        declarations = []
        for t in tools:
            properties = {}
            required = []
            for p in t.parameters:
                properties[p.name] = {"type": p.type.upper(), "description": p.description}
                if p.required:
                    required.append(p.name)
            declarations.append({
                "name": t.name,
                "description": t.description,
                "parameters": {"type": "OBJECT", "properties": properties, "required": required},
            })
        return [{"functionDeclarations": declarations}]

    def parse_response(self, raw: dict) -> MCPMessage:
        if "error" in raw:
            return MCPMessage(role=MCPRole.ASSISTANT, content=str(raw["error"]), message_type=MCPMessageType.ERROR)

        candidates = raw.get("candidates", [])
        if not candidates:
            return MCPMessage(role=MCPRole.ASSISTANT, content="Empty response", message_type=MCPMessageType.ERROR)

        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = []
        tool_calls = []
        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(MCPToolCall(name=fc.get("name", ""), arguments=fc.get("args", {})))

        content = "\n".join(text_parts)
        msg_type = MCPMessageType.TOOL_CALL if tool_calls else MCPMessageType.TEXT
        return MCPMessage(role=MCPRole.ASSISTANT, content=content, message_type=msg_type, tool_calls=tool_calls)

    async def complete(self, request: MCPRequest) -> MCPResponse:
        start = time.time()
        model = request.model or self.config.default_model
        url = f"{self.config.api_base}/models/{model}:generateContent"
        if self.config.api_key:
            url += f"?key={self.config.api_key}"

        contents, system_instruction = self.format_messages(request.messages)
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if request.tools:
            payload["tools"] = self.format_tools(request.tools)

        raw = await self._request_with_retry(url, payload)
        duration = int((time.time() - start) * 1000)

        if "error" in raw and "candidates" not in raw:
            return MCPResponse(
                status=MCPStatus.ERROR, error=str(raw.get("error", "")),
                model=model, provider=self.config.name,
                duration_ms=duration, request_id=request.request_id,
            )

        message = self.parse_response(raw)
        usage_data = raw.get("usageMetadata", {})
        usage = MCPUsage(
            prompt_tokens=usage_data.get("promptTokenCount", 0),
            completion_tokens=usage_data.get("candidatesTokenCount", 0),
            total_tokens=usage_data.get("totalTokenCount", 0),
        )
        self._stats["total_tokens_used"] += usage.total_tokens

        return MCPResponse(
            message=message, status=MCPStatus.OK, usage=usage,
            model=model, provider=self.config.name,
            duration_ms=duration, request_id=request.request_id,
        )

    async def stream(self, request: MCPRequest) -> AsyncIterator[MCPStreamChunk]:
        model = request.model or self.config.default_model
        url = f"{self.config.api_base}/models/{model}:streamGenerateContent?alt=sse"
        if self.config.api_key:
            url += f"&key={self.config.api_key}"

        contents, system_instruction = self.format_messages(request.messages)
        payload = {
            "contents": contents,
            "generationConfig": {"temperature": request.temperature, "maxOutputTokens": request.max_tokens},
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        async for line in self._stream_request(url, payload):
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            try:
                data = json.loads(data_str)
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        if "text" in part:
                            yield MCPStreamChunk(content=part["text"], delta_type="text")
                    finish = candidates[0].get("finishReason")
                    if finish and finish != "STOP":
                        continue
                    if finish == "STOP":
                        yield MCPStreamChunk(finish_reason="stop")
                        return
            except json.JSONDecodeError:
                continue


class CustomProvider(MCPProvider):
    def format_messages(self, messages: list[MCPMessage]) -> list[dict]:
        return [{"role": m.role.value, "content": m.content} for m in messages]

    def format_tools(self, tools: list[MCPToolDefinition]) -> list[dict]:
        return [t.to_dict() for t in tools]

    def parse_response(self, raw: dict) -> MCPMessage:
        if "error" in raw:
            return MCPMessage(role=MCPRole.ASSISTANT, content=str(raw["error"]), message_type=MCPMessageType.ERROR)
        content = raw.get("content") or raw.get("text") or raw.get("message") or raw.get("response", "")
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        return MCPMessage(role=MCPRole.ASSISTANT, content=str(content), message_type=MCPMessageType.TEXT)

    async def complete(self, request: MCPRequest) -> MCPResponse:
        start = time.time()
        stream_endpoint = self.config.capabilities.get("stream_endpoint", self.config.capabilities.get("endpoint", "/stream"))
        url = f"{self.config.api_base}{stream_endpoint}"
        payload = {
            "text": request.messages[-1].content if request.messages else "",
            "model": request.model or self.config.default_model,
            "provider": self.config.capabilities.get("provider_param", self.config.name),
        }

        content_parts = []
        try:
            async for line in self._stream_request(url, payload):
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        parsed = json.loads(data_str)
                        if isinstance(parsed, str):
                            content_parts.append(parsed)
                        elif isinstance(parsed, dict):
                            chunk_text = parsed.get("content") or parsed.get("text") or parsed.get("message", "")
                            if isinstance(chunk_text, dict):
                                chunk_text = json.dumps(chunk_text, ensure_ascii=False)
                            if chunk_text:
                                content_parts.append(str(chunk_text))
                        elif parsed is not None:
                            content_parts.append(str(parsed))
                    except json.JSONDecodeError:
                        if data_str.strip():
                            content_parts.append(data_str)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            if content_parts:
                pass
            else:
                return MCPResponse(
                    status=MCPStatus.ERROR, error=str(e),
                    model=request.model or self.config.default_model,
                    provider=self.config.name, duration_ms=duration,
                    request_id=request.request_id,
                )

        duration = int((time.time() - start) * 1000)
        full_content = "".join(content_parts).strip()
        if not full_content:
            return MCPResponse(
                status=MCPStatus.ERROR, error="Empty response from provider",
                model=request.model or self.config.default_model,
                provider=self.config.name, duration_ms=duration,
                request_id=request.request_id,
            )

        message = MCPMessage(role=MCPRole.ASSISTANT, content=full_content, message_type=MCPMessageType.TEXT)
        return MCPResponse(
            message=message, status=MCPStatus.OK,
            model=request.model or self.config.default_model,
            provider=self.config.name, duration_ms=duration,
            request_id=request.request_id,
        )

    async def stream(self, request: MCPRequest) -> AsyncIterator[MCPStreamChunk]:
        endpoint = self.config.capabilities.get("stream_endpoint", "/stream")
        url = f"{self.config.api_base}{endpoint}"
        payload = {
            "text": request.messages[-1].content if request.messages else "",
            "model": request.model or self.config.default_model,
            "provider": self.config.capabilities.get("provider_param", self.config.name),
        }

        async for line in self._stream_request(url, payload):
            if line.startswith("data: "):
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    yield MCPStreamChunk(finish_reason="stop")
                    return
                try:
                    parsed = json.loads(data_str)
                    if isinstance(parsed, str):
                        yield MCPStreamChunk(content=parsed, delta_type="text")
                    elif isinstance(parsed, dict):
                        content = parsed.get("content") or parsed.get("text") or parsed.get("message", "")
                        if isinstance(content, dict):
                            content = json.dumps(content, ensure_ascii=False)
                        yield MCPStreamChunk(content=str(content), delta_type="text")
                    elif parsed is not None:
                        yield MCPStreamChunk(content=str(parsed), delta_type="text")
                except json.JSONDecodeError:
                    yield MCPStreamChunk(content=data_str, delta_type="text")


PROVIDER_MAP = {
    MCPProviderType.OPENAI: OpenAIProvider,
    MCPProviderType.ANTHROPIC: AnthropicProvider,
    MCPProviderType.GOOGLE: GoogleProvider,
    MCPProviderType.CUSTOM: CustomProvider,
    MCPProviderType.LOCAL: CustomProvider,
}


def create_provider(config: MCPProviderConfig) -> MCPProvider:
    provider_class = PROVIDER_MAP.get(config.provider_type, CustomProvider)
    return provider_class(config)
