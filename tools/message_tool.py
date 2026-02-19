"""Message Tool - Logika untuk komunikasi dengan pengguna."""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class Message:
    def __init__(self, content: str, msg_type: str = "info", sender: str = "agent", recipient: str = "user"):
        self.content = content
        self.msg_type = msg_type
        self.sender = sender
        self.recipient = recipient
        self.timestamp = time.time()
        self.read = False

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "type": self.msg_type,
            "sender": self.sender,
            "recipient": self.recipient,
            "timestamp": self.timestamp,
            "read": self.read,
        }


class MessageTool:
    MSG_TYPES = {"info", "warning", "error", "success", "question", "progress"}

    def __init__(self, max_message_length: int = 10000):
        self.max_message_length = max_message_length
        self.messages: list[Message] = []
        self.pending_questions: list[Message] = []

    async def execute(self, plan: dict) -> str:
        intent = plan.get("intent", "")
        return (
            f"Message tool siap. Intent: {intent}. "
            f"Operasi: send, ask, notify, get_unread."
        )

    def send(self, content: str, msg_type: str = "info") -> dict:
        if len(content) > self.max_message_length:
            content = content[:self.max_message_length] + "... (terpotong)"

        if msg_type not in self.MSG_TYPES:
            msg_type = "info"

        msg = Message(content=content, msg_type=msg_type)
        self.messages.append(msg)
        logger.info(f"Pesan dikirim [{msg_type}]: {content[:100]}")

        return {"success": True, "message": msg.to_dict()}

    def ask(self, question: str, options: Optional[list[str]] = None) -> dict:
        msg = Message(content=question, msg_type="question")
        self.messages.append(msg)
        self.pending_questions.append(msg)

        result = {
            "success": True,
            "question": question,
            "options": options,
            "message": msg.to_dict(),
        }
        logger.info(f"Pertanyaan diajukan: {question[:100]}")
        return result

    def notify(self, title: str, body: str, level: str = "info") -> dict:
        content = f"**{title}**\n{body}"
        return self.send(content, msg_type=level)

    def progress(self, task: str, percentage: float, detail: str = "") -> dict:
        content = f"Progres [{task}]: {percentage:.0f}%"
        if detail:
            content += f" - {detail}"
        return self.send(content, msg_type="progress")

    def get_unread(self) -> list[dict]:
        unread = [msg for msg in self.messages if not msg.read]
        for msg in unread:
            msg.read = True
        return [msg.to_dict() for msg in unread]

    def get_history(self, limit: int = 50) -> list[dict]:
        return [msg.to_dict() for msg in self.messages[-limit:]]

    def get_pending_questions(self) -> list[dict]:
        return [msg.to_dict() for msg in self.pending_questions]

    def answer_question(self, answer: str) -> dict:
        if not self.pending_questions:
            return {"success": False, "error": "Tidak ada pertanyaan yang menunggu jawaban"}
        question = self.pending_questions.pop(0)
        question.read = True
        return {
            "success": True,
            "question": question.content,
            "answer": answer,
        }
