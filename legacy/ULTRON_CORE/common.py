from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Goal:
    text: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "pending"
    created_at: str = field(default_factory=now)


@dataclass
class Task:
    title: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "pending"
    dependencies: list = field(default_factory=list)
    attempts: int = 0
