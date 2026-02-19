"""MCP Client - Client tingkat tinggi untuk berkomunikasi via MCP protocol."""

import logging
import time
from typing import AsyncIterator, Optional

from mcp.protocol import (
    MCPMessage, MCPRequest, MCPResponse, MCPStreamChunk,
    MCPRole, MCPMessageType, MCPStatus, MCPToolDefinition,
    MCPToolCall, MCPToolResult, MCPProviderConfig,
)
from mcp.registry import MCPRegistry, create_default_registry

logger = logging.getLogger(__name__)


class MCPClient:
    def __init__(self, registry: Optional[MCPRegistry] = None):
        self.registry = registry or create_default_registry()
        self._current_model: str = ""
        self._current_provider: str = ""
        self._conversation: list[MCPMessage] = []
        self._system_prompt: str = ""

    def set_system_prompt(self, prompt: str):
        self._system_prompt = prompt

    def set_model(self, model: str, provider: str = "") -> bool:
        if provider:
            p = self.registry.get_provider(provider)
            if p and model in p.config.available_models:
                self._current_model = model
                self._current_provider = provider
                logger.info(f"MCP model diubah: {model} via {provider}")
                return True
        else:
            p = self.registry.get_provider_for_model(model)
            if p:
                self._current_model = model
                self._current_provider = p.config.name
                logger.info(f"MCP model diubah: {model} via {p.config.name}")
                return True

        all_models = self.registry.list_models()
        model_names = [m["model"] for m in all_models]
        logger.warning(f"Model '{model}' tidak ditemukan. Tersedia: {model_names}")
        return False

    def get_current_model(self) -> dict:
        return {
            "model": self._current_model,
            "provider": self._current_provider,
        }

    def add_message(self, role: str, content: str):
        mcp_role = MCPRole(role) if role in [r.value for r in MCPRole] else MCPRole.USER
        self._conversation.append(MCPMessage(role=mcp_role, content=content))

    def add_tool_result(self, call_id: str, name: str, content: str, success: bool = True, duration_ms: int = 0):
        result = MCPToolResult(call_id=call_id, name=name, content=content, success=success, duration_ms=duration_ms)
        self._conversation.append(
            MCPMessage(role=MCPRole.TOOL, content=content, message_type=MCPMessageType.TOOL_RESULT, tool_results=[result])
        )

    def clear_conversation(self):
        self._conversation.clear()

    def _build_request(self, user_message: str = "", stream: bool = False, tools: Optional[list[MCPToolDefinition]] = None) -> MCPRequest:
        messages = []
        if self._system_prompt:
            messages.append(MCPMessage(role=MCPRole.SYSTEM, content=self._system_prompt))
        messages.extend(self._conversation)
        if user_message:
            msg = MCPMessage(role=MCPRole.USER, content=user_message)
            messages.append(msg)
            self._conversation.append(msg)

        return MCPRequest(
            messages=messages,
            model=self._current_model,
            provider=self._current_provider,
            tools=tools or [],
            stream=stream,
        )

    async def chat(self, message: str, tools: Optional[list[MCPToolDefinition]] = None) -> str:
        request = self._build_request(user_message=message, tools=tools)
        response = await self.registry.complete(request)

        if response.status == MCPStatus.OK and response.message:
            self._conversation.append(response.message)
            return response.message.content
        elif response.error:
            return f"[MCP Error]: {response.error}"
        return "[MCP Error]: Empty response"

    async def chat_full(self, message: str, tools: Optional[list[MCPToolDefinition]] = None) -> MCPResponse:
        request = self._build_request(user_message=message, tools=tools)
        response = await self.registry.complete(request)
        if response.status == MCPStatus.OK and response.message:
            self._conversation.append(response.message)
        return response

    async def chat_stream(self, message: str, tools: Optional[list[MCPToolDefinition]] = None) -> AsyncIterator[str]:
        request = self._build_request(user_message=message, stream=True, tools=tools)
        content_parts = []

        async for chunk in self.registry.stream(request):
            if chunk.delta_type == "text" and chunk.content:
                content_parts.append(chunk.content)
                yield chunk.content
            elif chunk.delta_type == "error":
                yield f"[Error]: {chunk.content}"
                return
            if chunk.finish_reason:
                break

        full_content = "".join(content_parts)
        if full_content:
            self._conversation.append(MCPMessage(role=MCPRole.ASSISTANT, content=full_content))

    async def chat_stream_full(self, message: str, tools: Optional[list[MCPToolDefinition]] = None) -> AsyncIterator[MCPStreamChunk]:
        request = self._build_request(user_message=message, stream=True, tools=tools)
        content_parts = []

        async for chunk in self.registry.stream(request):
            if chunk.delta_type == "text" and chunk.content:
                content_parts.append(chunk.content)
            yield chunk
            if chunk.finish_reason:
                break

        full_content = "".join(content_parts)
        if full_content:
            self._conversation.append(MCPMessage(role=MCPRole.ASSISTANT, content=full_content))

    async def chat_with_context(self, messages: list[dict], tools: Optional[list[MCPToolDefinition]] = None) -> str:
        mcp_messages = []
        if self._system_prompt:
            mcp_messages.append(MCPMessage(role=MCPRole.SYSTEM, content=self._system_prompt))

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            mcp_role = MCPRole(role) if role in [r.value for r in MCPRole] else MCPRole.USER
            mcp_messages.append(MCPMessage(role=mcp_role, content=content))

        request = MCPRequest(
            messages=mcp_messages,
            model=self._current_model,
            provider=self._current_provider,
            tools=tools or [],
        )
        response = await self.registry.complete(request)
        if response.status == MCPStatus.OK and response.message:
            return response.message.content
        return response.error or "[MCP Error]: Empty response"

    def register_provider(self, config: MCPProviderConfig) -> bool:
        return self.registry.register_provider(config)

    def list_providers(self) -> list[dict]:
        return self.registry.list_providers()

    def list_models(self) -> list[dict]:
        return self.registry.list_models()

    def get_stats(self) -> dict:
        stats = self.registry.get_stats()
        stats["current_model"] = self._current_model
        stats["current_provider"] = self._current_provider
        stats["conversation_length"] = len(self._conversation)
        return stats

    async def health_check(self) -> dict:
        return await self.registry.health_check()

    async def close(self):
        await self.registry.close_all()
