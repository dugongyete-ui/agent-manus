"""MCP Transport - Layer transport untuk stdio dan HTTP/SSE."""

import asyncio
import json
import logging
import sys
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from mcp.protocol import MCPRequest, MCPResponse, MCPStreamChunk, MCPMessage
from mcp.server import MCPServer

logger = logging.getLogger(__name__)


class MCPTransport(ABC):
    @abstractmethod
    async def send(self, data: dict) -> None:
        pass

    @abstractmethod
    async def receive(self) -> Optional[dict]:
        pass

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass


class StdioTransport(MCPTransport):
    def __init__(self, server: MCPServer):
        self.server = server
        self._running = False

    async def send(self, data: dict) -> None:
        line = json.dumps(data, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    async def receive(self) -> Optional[dict]:
        loop = asyncio.get_event_loop()
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                return None
            return json.loads(line.strip())
        except (json.JSONDecodeError, EOFError):
            return None

    async def start(self) -> None:
        self._running = True
        await self.server.start()
        logger.info("MCP Stdio Transport dimulai")

        while self._running:
            data = await self.receive()
            if data is None:
                await asyncio.sleep(0.1)
                continue

            method = data.get("method", "")
            params = data.get("params", {})
            request_id = data.get("id", "")

            try:
                result = await self._handle_method(method, params)
                response = {"jsonrpc": "2.0", "id": request_id, "result": result}
            except Exception as e:
                response = {
                    "jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32603, "message": str(e)},
                }

            await self.send(response)

    async def stop(self) -> None:
        self._running = False
        await self.server.stop()

    async def _handle_method(self, method: str, params: dict) -> dict:
        if method == "mcp/complete":
            return await self.server.handle_complete(params)
        elif method == "mcp/chat":
            return await self.server.handle_chat(params)
        elif method == "mcp/list_providers":
            return self.server.handle_list_providers()
        elif method == "mcp/list_models":
            return self.server.handle_list_models()
        elif method == "mcp/register_provider":
            return await self.server.handle_register_provider(params)
        elif method == "mcp/switch_model":
            return self.server.handle_switch_model(params.get("model", ""), params.get("provider", ""))
        elif method == "mcp/health":
            return await self.server.handle_health()
        elif method == "mcp/stats":
            return self.server.handle_stats()
        else:
            return {"error": f"Method tidak dikenal: {method}"}


class HTTPTransport(MCPTransport):
    def __init__(self, server: MCPServer):
        self.server = server

    async def send(self, data: dict) -> None:
        pass

    async def receive(self) -> Optional[dict]:
        return None

    async def start(self) -> None:
        await self.server.start()
        logger.info("MCP HTTP Transport siap")

    async def stop(self) -> None:
        await self.server.stop()

    async def handle_request(self, method: str, data: dict) -> dict:
        if method == "complete":
            return await self.server.handle_complete(data)
        elif method == "chat":
            return await self.server.handle_chat(data)
        elif method == "list_providers":
            return self.server.handle_list_providers()
        elif method == "list_models":
            return self.server.handle_list_models()
        elif method == "register_provider":
            return await self.server.handle_register_provider(data)
        elif method == "unregister_provider":
            return self.server.handle_unregister_provider(data.get("name", ""))
        elif method == "switch_model":
            return self.server.handle_switch_model(data.get("model", ""), data.get("provider", ""))
        elif method == "toggle_provider":
            return self.server.handle_toggle_provider(data.get("name", ""), data.get("enabled", True))
        elif method == "set_api_key":
            return self.server.handle_set_api_key(data.get("name", ""), data.get("api_key", ""))
        elif method == "health":
            return await self.server.handle_health()
        elif method == "stats":
            return self.server.handle_stats()
        elif method == "request_log":
            return self.server.handle_request_log(data.get("limit", 20))
        else:
            return {"error": f"Method tidak dikenal: {method}"}

    async def handle_stream(self, data: dict) -> AsyncIterator[dict]:
        async for chunk_data in self.server.handle_stream(data):
            yield chunk_data
