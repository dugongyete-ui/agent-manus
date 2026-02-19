"""MCP Registry - Manajemen provider dan routing request ke provider yang tepat."""

import logging
import time
from typing import AsyncIterator, Optional

from mcp.protocol import (
    MCPProviderConfig, MCPProviderType, MCPRequest, MCPResponse,
    MCPStreamChunk, MCPStatus, MCPMessage, MCPRole, MCPToolDefinition,
)
from mcp.providers import MCPProvider, create_provider

logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://22f0ee02-5482-4584-a7aa-bb5f61e50c6b-00-iq4otn6awuiy.janeway.replit.dev"


class MCPRegistry:
    def __init__(self):
        self._providers: dict[str, MCPProvider] = {}
        self._model_to_provider: dict[str, str] = {}
        self._default_provider: Optional[str] = None
        self._tool_definitions: list[MCPToolDefinition] = []
        self._request_log: list[dict] = []
        self._max_log_entries = 100

    def register_provider(self, config: MCPProviderConfig) -> bool:
        try:
            provider = create_provider(config)
            self._providers[config.name] = provider
            for model in config.available_models:
                self._model_to_provider[model] = config.name
            if not self._default_provider or config.name == "default":
                self._default_provider = config.name
            logger.info(f"MCP Provider terdaftar: {config.name} ({config.provider_type.value}) dengan {len(config.available_models)} model")
            return True
        except Exception as e:
            logger.error(f"Gagal registrasi provider {config.name}: {e}")
            return False

    def unregister_provider(self, name: str) -> bool:
        if name in self._providers:
            models_to_remove = [m for m, p in self._model_to_provider.items() if p == name]
            for m in models_to_remove:
                del self._model_to_provider[m]
            del self._providers[name]
            if self._default_provider == name:
                self._default_provider = next(iter(self._providers), None)
            logger.info(f"MCP Provider dihapus: {name}")
            return True
        return False

    def get_provider(self, name: str) -> Optional[MCPProvider]:
        return self._providers.get(name)

    def get_provider_for_model(self, model: str) -> Optional[MCPProvider]:
        provider_name = self._model_to_provider.get(model)
        if provider_name:
            return self._providers.get(provider_name)
        return self._providers.get(self._default_provider) if self._default_provider else None

    def get_default_provider(self) -> Optional[MCPProvider]:
        if self._default_provider:
            return self._providers.get(self._default_provider)
        return None

    def set_default_provider(self, name: str) -> bool:
        if name in self._providers:
            self._default_provider = name
            return True
        return False

    def register_tool(self, tool_def: MCPToolDefinition):
        existing = [i for i, t in enumerate(self._tool_definitions) if t.name == tool_def.name]
        if existing:
            self._tool_definitions[existing[0]] = tool_def
        else:
            self._tool_definitions.append(tool_def)

    def get_tools(self) -> list[MCPToolDefinition]:
        return self._tool_definitions.copy()

    def list_providers(self) -> list[dict]:
        result = []
        for name, provider in self._providers.items():
            info = provider.config.to_dict()
            info["is_default"] = name == self._default_provider
            info["stats"] = provider.get_stats()
            result.append(info)
        return result

    def list_models(self) -> list[dict]:
        models = []
        for model, provider_name in self._model_to_provider.items():
            provider = self._providers.get(provider_name)
            if provider:
                models.append({
                    "model": model,
                    "provider": provider_name,
                    "provider_type": provider.config.provider_type.value,
                    "enabled": provider.config.enabled,
                })
        return models

    async def complete(self, request: MCPRequest) -> MCPResponse:
        provider = self._resolve_provider(request)
        if not provider:
            return MCPResponse(
                status=MCPStatus.ERROR,
                error=f"Provider tidak ditemukan untuk model '{request.model}' atau provider '{request.provider}'",
                request_id=request.request_id,
            )

        if not provider.config.enabled:
            return MCPResponse(
                status=MCPStatus.ERROR,
                error=f"Provider '{provider.config.name}' sedang nonaktif",
                request_id=request.request_id,
            )

        if request.tools or self._tool_definitions:
            tools = request.tools or self._tool_definitions
            request.tools = tools

        start = time.time()
        try:
            response = await provider.complete(request)
            self._log_request(request, response, int((time.time() - start) * 1000))
            return response
        except Exception as e:
            logger.error(f"MCP complete error: {e}")
            return MCPResponse(
                status=MCPStatus.ERROR, error=str(e),
                model=request.model, provider=provider.config.name,
                duration_ms=int((time.time() - start) * 1000),
                request_id=request.request_id,
            )

    async def stream(self, request: MCPRequest) -> AsyncIterator[MCPStreamChunk]:
        provider = self._resolve_provider(request)
        if not provider:
            yield MCPStreamChunk(content=f"Provider tidak ditemukan", delta_type="error", finish_reason="error")
            return

        if not provider.config.enabled:
            yield MCPStreamChunk(content=f"Provider '{provider.config.name}' nonaktif", delta_type="error", finish_reason="error")
            return

        try:
            async for chunk in provider.stream(request):
                yield chunk
        except Exception as e:
            logger.error(f"MCP stream error: {e}")
            yield MCPStreamChunk(content=str(e), delta_type="error", finish_reason="error")

    def _resolve_provider(self, request: MCPRequest) -> Optional[MCPProvider]:
        if request.provider and request.provider in self._providers:
            return self._providers[request.provider]
        if request.model:
            provider = self.get_provider_for_model(request.model)
            if provider:
                return provider
        return self.get_default_provider()

    def _log_request(self, request: MCPRequest, response: MCPResponse, duration_ms: int):
        entry = {
            "request_id": request.request_id,
            "model": request.model,
            "provider": response.provider,
            "status": response.status.value,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        }
        if response.usage:
            entry["tokens"] = response.usage.total_tokens
        self._request_log.append(entry)
        if len(self._request_log) > self._max_log_entries:
            self._request_log = self._request_log[-self._max_log_entries:]

    def get_request_log(self, limit: int = 20) -> list[dict]:
        return self._request_log[-limit:]

    def get_stats(self) -> dict:
        total_requests = sum(p.get_stats()["total_requests"] for p in self._providers.values())
        total_tokens = sum(p.get_stats()["total_tokens_used"] for p in self._providers.values())
        total_failures = sum(p.get_stats()["total_failures"] for p in self._providers.values())
        return {
            "total_providers": len(self._providers),
            "total_models": len(self._model_to_provider),
            "total_tools": len(self._tool_definitions),
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_failures": total_failures,
            "default_provider": self._default_provider,
            "providers": {name: p.get_stats() for name, p in self._providers.items()},
        }

    async def health_check(self) -> dict:
        results = {}
        for name, provider in self._providers.items():
            results[name] = await provider.health_check()
        return {
            "status": "healthy" if self._providers else "no_providers",
            "providers": results,
            "default": self._default_provider,
        }

    async def close_all(self):
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
        self._model_to_provider.clear()
        self._default_provider = None


def create_default_registry() -> MCPRegistry:
    registry = MCPRegistry()

    custom_config = MCPProviderConfig(
        provider_type=MCPProviderType.CUSTOM,
        name="dzeck",
        api_base=DEFAULT_API_BASE,
        default_model="claude40opusthinking_labs",
        available_models=[
            "gpt5_thinking", "03", "o3pro", "claude40opus",
            "claude40opusthinking", "claude41opusthinking",
            "claude45sonnet", "claude45sonnetthinking", "grok4",
            "o3_research", "o3pro_research", "claude40sonnetthinking_research",
            "o3pro_labs", "claude40opusthinking_labs", "r1",
        ],
        timeout=120,
        max_retries=5,
        capabilities={
            "endpoint": "/stream",
            "stream_endpoint": "/stream",
            "provider_param": "Perplexity",
        },
        enabled=True,
    )
    registry.register_provider(custom_config)

    openai_config = MCPProviderConfig(
        provider_type=MCPProviderType.OPENAI,
        name="openai",
        api_base="https://api.openai.com/v1",
        default_model="gpt-4o",
        available_models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini", "o3-mini"],
        timeout=120,
        max_retries=3,
        enabled=False,
    )
    registry.register_provider(openai_config)

    anthropic_config = MCPProviderConfig(
        provider_type=MCPProviderType.ANTHROPIC,
        name="anthropic",
        api_base="https://api.anthropic.com/v1",
        default_model="claude-sonnet-4-20250514",
        available_models=["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
        timeout=120,
        max_retries=3,
        headers={"anthropic-version": "2023-06-01"},
        enabled=False,
    )
    registry.register_provider(anthropic_config)

    google_config = MCPProviderConfig(
        provider_type=MCPProviderType.GOOGLE,
        name="google",
        api_base="https://generativelanguage.googleapis.com/v1beta",
        default_model="gemini-2.0-flash",
        available_models=["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        timeout=120,
        max_retries=3,
        enabled=False,
    )
    registry.register_provider(google_config)

    registry.set_default_provider("dzeck")

    return registry
