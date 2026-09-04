"""
ui.mobile.api.schemas - request/response shapes for the mobile REST API.

Kept as plain dataclasses (no pydantic dependency) since the rest of
this UI layer only depends on Flask. If the project later adopts
FastAPI/pydantic for the mobile API, these map over directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class ChatRequest:
    message: str
    session_id: str | None = None

    @staticmethod
    def from_json(payload: dict) -> "ChatRequest":
        message = (payload.get("message") or "").strip()
        if not message:
            raise ValueError("message is required")
        return ChatRequest(message=message, session_id=payload.get("session_id"))


@dataclass
class ChatResponse:
    session_id: str
    reply: str
    source: str
    timestamp: float

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class StatusResponse:
    assistant: bool
    auth: bool
    health_check: bool

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class ErrorResponse:
    error: str

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class NotificationItem:
    id: str
    level: str
    title: str
    message: str
    source: str
    timestamp: float

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class NotificationsResponse:
    notifications: list

    def to_json(self) -> dict:
        return {"notifications": self.notifications}
