"""Context Manager - Mengelola konteks percakapan dan memori agen."""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class Message:
    def __init__(self, role: str, content: str, metadata: Optional[dict] = None):
        self.role = role
        self.content = content
        self.metadata = metadata or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class ContextManager:
    def __init__(self, max_tokens: int = 128000, memory_window: int = 20, summarization_threshold: int = 15):
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.summarization_threshold = summarization_threshold
        self.messages: list[Message] = []
        self.summary: str = ""
        self.system_prompt: str = ""
        self.metadata: dict = {}

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt
        logger.info("System prompt diperbarui.")

    def add_message(self, role: str, content: str, metadata: Optional[dict] = None):
        msg = Message(role=role, content=content, metadata=metadata)
        self.messages.append(msg)
        logger.debug(f"Pesan ditambahkan dari {role}, total: {len(self.messages)}")
        if len(self.messages) > self.summarization_threshold:
            self._summarize_old_messages()

    def get_context_window(self) -> list[dict]:
        context = []
        if self.system_prompt:
            context.append({"role": "system", "content": self.system_prompt})
        if self.summary:
            context.append({"role": "system", "content": f"Ringkasan percakapan sebelumnya:\n{self.summary}"})
        recent = self.messages[-self.memory_window:]
        for msg in recent:
            context.append(msg.to_dict())
        return context

    def _summarize_old_messages(self):
        if len(self.messages) <= self.memory_window:
            return
        old_messages = self.messages[:-self.memory_window]
        summary_parts = []
        for msg in old_messages:
            summary_parts.append(f"[{msg.role}]: {msg.content[:200]}")
        self.summary += "\n".join(summary_parts) + "\n"
        self.messages = self.messages[-self.memory_window:]
        logger.info(f"Konteks diringkas, {len(old_messages)} pesan lama diarsipkan.")

    def get_token_estimate(self) -> int:
        total_text = self.system_prompt + self.summary
        for msg in self.messages:
            total_text += msg.content
        return len(total_text) // 4

    def clear(self):
        self.messages.clear()
        self.summary = ""
        self.metadata.clear()
        logger.info("Konteks dibersihkan.")

    def export_history(self) -> list[dict]:
        return [msg.to_dict() for msg in self.messages]
