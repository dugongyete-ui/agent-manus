"""MCP Protocol - Definisi tipe data dan format pesan standar untuk Model Context Protocol."""

import time
import uuid
from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, field, asdict


class MCPRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class MCPMessageType(str, Enum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    STREAM_CHUNK = "stream_chunk"
    STREAM_END = "stream_end"


class MCPProviderType(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    LOCAL = "local"
    CUSTOM = "custom"


class MCPTransportType(str, Enum):
    HTTP = "http"
    SSE = "sse"
    STDIO = "stdio"
    WEBSOCKET = "websocket"


class MCPStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UNAUTHORIZED = "unauthorized"


@dataclass
class MCPToolParameter:
    name: str
    type: str
    description: str = ""
    required: bool = False
    default: Any = None
    enum: Optional[list] = None

    def to_dict(self) -> dict:
        d = {"name": self.name, "type": self.type, "description": self.description, "required": self.required}
        if self.default is not None:
            d["default"] = self.default
        if self.enum is not None:
            d["enum"] = self.enum
        return d


@dataclass
class MCPToolDefinition:
    name: str
    description: str
    parameters: list[MCPToolParameter] = field(default_factory=list)
    returns: str = "string"
    category: str = "general"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "returns": self.returns,
            "category": self.category,
        }

    def to_openai_schema(self) -> dict:
        properties = {}
        required = []
        for p in self.parameters:
            prop = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def to_anthropic_schema(self) -> dict:
        properties = {}
        required = []
        for p in self.parameters:
            prop = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


@dataclass
class MCPToolCall:
    id: str = ""
    name: str = ""
    arguments: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = f"call_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}


@dataclass
class MCPToolResult:
    call_id: str = ""
    name: str = ""
    content: str = ""
    success: bool = True
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "content": self.content,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }


@dataclass
class MCPMessage:
    role: MCPRole
    content: str = ""
    message_type: MCPMessageType = MCPMessageType.TEXT
    tool_calls: list[MCPToolCall] = field(default_factory=list)
    tool_results: list[MCPToolResult] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    id: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.id:
            self.id = f"msg_{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "role": self.role.value,
            "content": self.content,
            "message_type": self.message_type.value,
            "timestamp": self.timestamp,
        }
        if self.tool_calls:
            d["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.tool_results:
            d["tool_results"] = [tr.to_dict() for tr in self.tool_results]
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MCPMessage":
        tool_calls = [MCPToolCall(**tc) for tc in data.get("tool_calls", [])]
        tool_results = [MCPToolResult(**tr) for tr in data.get("tool_results", [])]
        return cls(
            role=MCPRole(data.get("role", "user")),
            content=data.get("content", ""),
            message_type=MCPMessageType(data.get("message_type", "text")),
            tool_calls=tool_calls,
            tool_results=tool_results,
            metadata=data.get("metadata", {}),
            id=data.get("id", ""),
            timestamp=data.get("timestamp", 0.0),
        )


@dataclass
class MCPRequest:
    messages: list[MCPMessage] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    tools: list[MCPToolDefinition] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    stop_sequences: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    request_id: str = ""

    def __post_init__(self):
        if not self.request_id:
            self.request_id = f"req_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "messages": [m.to_dict() for m in self.messages],
            "model": self.model,
            "provider": self.provider,
            "tools": [t.to_dict() for t in self.tools],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
            "stop_sequences": self.stop_sequences,
            "metadata": self.metadata,
        }


@dataclass
class MCPUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MCPResponse:
    message: Optional[MCPMessage] = None
    status: MCPStatus = MCPStatus.OK
    usage: Optional[MCPUsage] = None
    model: str = ""
    provider: str = ""
    error: str = ""
    duration_ms: int = 0
    request_id: str = ""
    response_id: str = ""

    def __post_init__(self):
        if not self.response_id:
            self.response_id = f"resp_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> dict:
        d = {
            "response_id": self.response_id,
            "request_id": self.request_id,
            "status": self.status.value,
            "model": self.model,
            "provider": self.provider,
            "duration_ms": self.duration_ms,
        }
        if self.message:
            d["message"] = self.message.to_dict()
        if self.usage:
            d["usage"] = self.usage.to_dict()
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class MCPProviderConfig:
    provider_type: MCPProviderType
    name: str
    api_base: str = ""
    api_key: str = ""
    default_model: str = ""
    available_models: list[str] = field(default_factory=list)
    timeout: int = 120
    max_retries: int = 3
    headers: dict = field(default_factory=dict)
    capabilities: dict = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provider_type"] = self.provider_type.value
        if "api_key" in d and d["api_key"]:
            d["api_key"] = d["api_key"][:4] + "****"
        return d


@dataclass
class MCPStreamChunk:
    content: str = ""
    delta_type: str = "text"
    tool_call: Optional[MCPToolCall] = None
    finish_reason: Optional[str] = None
    usage: Optional[MCPUsage] = None

    def to_dict(self) -> dict:
        d = {"content": self.content, "delta_type": self.delta_type}
        if self.tool_call:
            d["tool_call"] = self.tool_call.to_dict()
        if self.finish_reason:
            d["finish_reason"] = self.finish_reason
        if self.usage:
            d["usage"] = self.usage.to_dict()
        return d
