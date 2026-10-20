"""Data models for authentication, users, and roles."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class Role(str, Enum):
    """User authorization roles."""

    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


@dataclass(slots=True)
class User:
    """Authenticated user entity."""

    id: str
    username: str
    role: str = Role.USER.value
    created_at: float = field(default_factory=time.time)
    is_active: bool = True

    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value

    def can_execute_shell(self) -> bool:
        return self.role == Role.ADMIN.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at,
            "is_active": self.is_active,
        }


@dataclass(slots=True)
class UserSession:
    """Active session instance."""

    token_hash: str
    user_id: str
    created_at: float
    expires_at: float
    revoked: bool = False

    def is_valid(self) -> bool:
        return (not self.revoked) and (time.time() < self.expires_at)
