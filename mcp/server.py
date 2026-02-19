"""MCP Server - Server yang menangani request MCP protocol via HTTP/SSE."""

import asyncio
import json
import logging
import time
from typing import Optional

from mcp.protocol import (
    MCPMessage, MCPRequest, MCPResponse, MCPStreamChunk,
    MCPRole, MCPMessageType, MCPStatus, MCPProviderConfig,
    MCPProviderType, MCPToolDefinition, MCPToolParameter,
)
from mcp.registry import MCPRegistry, create_default_registry
from mcp.client import MCPClient

logger = logging.getLogger(__name__)


class MCPServer:
    def __init__(self, registry: Optional[MCPRegistry] = None):
        self.registry = registry or create_default_registry()
        self.client = MCPClient(self.registry)
        self._request_handlers: dict = {}
        self._started = False

    async def start(self):
        self._started = True
        logger.info("MCP Server dimulai")

    async def stop(self):
        await self.registry.close_all()
        self._started = False
        logger.info("MCP Server dihentikan")

    async def handle_complete(self, data: dict) -> dict:
        try:
            messages = [MCPMessage.from_dict(m) for m in data.get("messages", [])]
            request = MCPRequest(
                messages=messages,
                model=data.get("model", ""),
                provider=data.get("provider", ""),
                temperature=data.get("temperature", 0.7),
                max_tokens=data.get("max_tokens", 4096),
            )

            if "tools" in data:
                for td in data["tools"]:
                    params = [MCPToolParameter(**p) for p in td.get("parameters", [])]
                    request.tools.append(MCPToolDefinition(
                        name=td["name"],
                        description=td.get("description", ""),
                        parameters=params,
                    ))

            response = await self.registry.complete(request)
            return response.to_dict()

        except Exception as e:
            logger.error(f"MCP handle_complete error: {e}")
            return MCPResponse(status=MCPStatus.ERROR, error=str(e)).to_dict()

    async def handle_stream(self, data: dict):
        try:
            messages = [MCPMessage.from_dict(m) for m in data.get("messages", [])]
            request = MCPRequest(
                messages=messages,
                model=data.get("model", ""),
                provider=data.get("provider", ""),
                temperature=data.get("temperature", 0.7),
                max_tokens=data.get("max_tokens", 4096),
                stream=True,
            )

            async for chunk in self.registry.stream(request):
                yield chunk.to_dict()

        except Exception as e:
            logger.error(f"MCP handle_stream error: {e}")
            yield {"error": str(e), "delta_type": "error"}

    async def handle_chat(self, data: dict) -> dict:
        message = data.get("message", "")
        model = data.get("model", "")
        provider = data.get("provider", "")
        system_prompt = data.get("system_prompt", "")

        if system_prompt:
            self.client.set_system_prompt(system_prompt)
        if model:
            self.client.set_model(model, provider)

        response = await self.client.chat_full(message)
        return response.to_dict()

    def handle_list_providers(self) -> dict:
        return {
            "providers": self.registry.list_providers(),
            "default": self.registry._default_provider,
        }

    def handle_list_models(self) -> dict:
        return {
            "models": self.registry.list_models(),
            "current": self.client.get_current_model(),
        }

    async def handle_register_provider(self, data: dict) -> dict:
        try:
            provider_type = MCPProviderType(data.get("type", "custom"))
            config = MCPProviderConfig(
                provider_type=provider_type,
                name=data.get("name", ""),
                api_base=data.get("api_base", ""),
                api_key=data.get("api_key", ""),
                default_model=data.get("default_model", ""),
                available_models=data.get("models", []),
                timeout=data.get("timeout", 120),
                max_retries=data.get("max_retries", 3),
                headers=data.get("headers", {}),
                capabilities=data.get("capabilities", {}),
                enabled=data.get("enabled", True),
            )
            success = self.registry.register_provider(config)
            return {"ok": success, "provider": config.name}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def handle_unregister_provider(self, name: str) -> dict:
        success = self.registry.unregister_provider(name)
        return {"ok": success, "provider": name}

    def handle_switch_model(self, model: str, provider: str = "") -> dict:
        success = self.client.set_model(model, provider)
        return {"ok": success, "current": self.client.get_current_model()}

    def handle_toggle_provider(self, name: str, enabled: bool) -> dict:
        provider = self.registry.get_provider(name)
        if provider:
            provider.config.enabled = enabled
            return {"ok": True, "provider": name, "enabled": enabled}
        return {"ok": False, "error": f"Provider '{name}' tidak ditemukan"}

    def handle_set_api_key(self, name: str, api_key: str) -> dict:
        provider = self.registry.get_provider(name)
        if provider:
            provider.config.api_key = api_key
            provider.config.enabled = True
            return {"ok": True, "provider": name}
        return {"ok": False, "error": f"Provider '{name}' tidak ditemukan"}

    async def handle_health(self) -> dict:
        return await self.registry.health_check()

    def handle_stats(self) -> dict:
        return self.client.get_stats()

    def handle_request_log(self, limit: int = 20) -> dict:
        return {"log": self.registry.get_request_log(limit)}
