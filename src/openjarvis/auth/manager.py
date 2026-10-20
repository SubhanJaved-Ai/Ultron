"""Thread-safe SQLite user and session manager for multi-user OpenJarvis."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
import uuid
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional

from openjarvis.auth.crypto import (
    generate_session_token,
    hash_password,
    hash_token,
    needs_rehash,
    verify_password,
)
from openjarvis.auth.models import Role, User
from openjarvis.core.paths import get_config_dir

logger = logging.getLogger(__name__)


def _db_locked(func):
    """Serialize database access across threads."""

    @wraps(func)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return func(self, *args, **kwargs)

    return wrapped


class UserManager:
    """Manages users, authentication, sessions, and per-user preferences."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            config_dir = get_config_dir()
            config_dir.mkdir(parents=True, exist_ok=True)
            self._db_path = str(config_dir / "users.db")
        else:
            self._db_path = str(db_path)

        self._lock = threading.RLock()
        if self._db_path != ":memory:":
            from openjarvis.security.file_utils import secure_create

            secure_create(Path(self._db_path))

        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    @_db_locked
    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt          TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'user',
                created_at    REAL NOT NULL,
                is_active     INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

            CREATE TABLE IF NOT EXISTS user_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                revoked    INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON user_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at);

            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id    TEXT NOT NULL,
                key        TEXT NOT NULL,
                value      TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_id, key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS auth_audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp  REAL NOT NULL,
                event      TEXT NOT NULL,
                user_id    TEXT,
                ip         TEXT DEFAULT '',
                details    TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_audit_time ON auth_audit_log(timestamp);

            CREATE TABLE IF NOT EXISTS failed_logins (
                key          TEXT PRIMARY KEY,
                attempts     INTEGER NOT NULL DEFAULT 0,
                last_attempt REAL NOT NULL,
                locked_until REAL NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_failed_logins_key ON failed_logins(key);
        """)
        self._conn.commit()

    @_db_locked
    def count_users(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]

    @_db_locked
    def register(
        self,
        username: str,
        password: str,
        role: str = Role.USER.value,
    ) -> User:
        """Register a new user with PBKDF2 password hashing.

        Bootstrap guard: The very first registered user is automatically
        assigned the ADMIN role. Subsequent registrations can NEVER be granted
        admin privileges through the self-registration endpoint.
        """
        uname = (username or "").strip().lower()
        if not uname or len(uname) < 3:
            raise ValueError("Username must be at least 3 characters.")
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")

        # Registration privilege guard:
        # Only the very first user bootstrap becomes admin; all others are forced to user role
        if self.count_users() == 0:
            assigned_role = Role.ADMIN.value
        else:
            assigned_role = Role.USER.value

        pwd_hash, salt = hash_password(password)
        user_id = str(uuid.uuid4())
        now = time.time()

        try:
            self._conn.execute(
                """
                INSERT INTO users (id, username, password_hash, salt, role, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (user_id, uname, pwd_hash, salt, assigned_role, now),
            )
            self._conn.commit()
            self._record_audit_unlocked(
                "user_registered", user_id, details=f"username={uname},role={assigned_role}"
            )
            return User(
                id=user_id, username=uname, role=assigned_role, created_at=now, is_active=True
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{uname}' already exists.")

    def _record_failed_attempt_unlocked(self, key: str, now: float) -> None:
        """Track failed login attempts and lock out account if threshold exceeded (>=5 in 15m)."""
        row = self._conn.execute(
            "SELECT attempts, last_attempt FROM failed_logins WHERE key = ?",
            (key,),
        ).fetchone()
        if row:
            attempts = row["attempts"] + 1 if (now - row["last_attempt"] < 900.0) else 1
            locked_until = (now + 900.0) if attempts >= 5 else 0.0
            self._conn.execute(
                "UPDATE failed_logins SET attempts = ?, last_attempt = ?, locked_until = ? WHERE key = ?",
                (attempts, now, locked_until, key),
            )
        else:
            self._conn.execute(
                "INSERT INTO failed_logins (key, attempts, last_attempt, locked_until) VALUES (?, 1, ?, 0.0)",
                (key, now),
            )
        self._conn.commit()

    @_db_locked
    def is_locked(self, username: str) -> bool:
        """Check whether a user account is locked due to repeated failed logins."""
        uname = (username or "").strip().lower()
        now = time.time()
        row = self._conn.execute(
            "SELECT locked_until FROM failed_logins WHERE key = ?",
            (f"user:{uname}",),
        ).fetchone()
        return bool(row and row["locked_until"] > now)

    @_db_locked
    def reset_lockout(self, username: str) -> None:
        """Manually clear failed login counter / lockout for a user."""
        uname = (username or "").strip().lower()
        self._conn.execute("DELETE FROM failed_logins WHERE key = ?", (f"user:{uname}",))
        self._conn.commit()

    @_db_locked
    def authenticate(
        self, username: str, password: str, ip: str = ""
    ) -> Optional[User]:
        """Authenticate user with login throttling, account lockout, and transparent rehash."""
        uname = (username or "").strip().lower()
        now = time.time()
        throttle_key = f"user:{uname}"

        # 1. Enforce account lockout
        lock_row = self._conn.execute(
            "SELECT attempts, locked_until FROM failed_logins WHERE key = ?",
            (throttle_key,),
        ).fetchone()
        if lock_row and lock_row["locked_until"] > now:
            self._record_audit_unlocked(
                "auth_failed_locked_out", "", ip=ip, details=f"username={uname}"
            )
            return None

        # 2. Look up user
        row = self._conn.execute(
            "SELECT id, username, password_hash, salt, role, created_at, is_active FROM users WHERE username = ?",
            (uname,),
        ).fetchone()
        if not row:
            self._record_audit_unlocked(
                "auth_failed_user_not_found", "", ip=ip, details=f"username={uname}"
            )
            self._record_failed_attempt_unlocked(throttle_key, now)
            return None

        if not bool(row["is_active"]):
            self._record_audit_unlocked("auth_failed_user_inactive", row["id"], ip=ip)
            return None

        # 3. Timing-safe password verification
        if not verify_password(password, row["password_hash"], row["salt"]):
            self._record_audit_unlocked(
                "auth_failed_invalid_password", row["id"], ip=ip
            )
            self._record_failed_attempt_unlocked(throttle_key, now)
            return None

        # 4. Success: clear failed login counter
        self._conn.execute("DELETE FROM failed_logins WHERE key = ?", (throttle_key,))

        # 5. Transparent zero-downtime hash upgrade if work factor is below current standard
        if needs_rehash(row["password_hash"]):
            new_hash, new_salt = hash_password(password)
            self._conn.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
                (new_hash, new_salt, row["id"]),
            )
            self._record_audit_unlocked("user_password_rehashed", row["id"], ip=ip)

        self._conn.commit()
        self._record_audit_unlocked("auth_success", row["id"], ip=ip)
        return User(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
        )

    @_db_locked
    def create_session(self, user_id: str, ttl_seconds: float = 86400.0) -> str:
        """Create a session token for user. Returns plain token, stores hash."""
        token = generate_session_token()
        t_hash = hash_token(token)
        now = time.time()
        expires = now + ttl_seconds

        self._conn.execute(
            """
            INSERT INTO user_sessions (token_hash, user_id, created_at, expires_at, revoked)
            VALUES (?, ?, ?, ?, 0)
            """,
            (t_hash, user_id, now, expires),
        )
        self._conn.commit()
        return token

    @_db_locked
    def validate_session(self, token: str) -> Optional[User]:
        """Validate session token and return user if active and not expired."""
        if not token:
            return None
        t_hash = hash_token(token)
        now = time.time()

        row = self._conn.execute(
            """
            SELECT s.expires_at, s.revoked, u.id, u.username, u.role, u.created_at, u.is_active
            FROM user_sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token_hash = ?
            """,
            (t_hash,),
        ).fetchone()

        if not row:
            return None
        if (
            bool(row["revoked"])
            or (now >= row["expires_at"])
            or not bool(row["is_active"])
        ):
            return None

        return User(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
        )

    @_db_locked
    def revoke_session(self, token: str) -> bool:
        """Revoke a single session token."""
        if not token:
            return False
        t_hash = hash_token(token)
        cur = self._conn.execute(
            "UPDATE user_sessions SET revoked = 1 WHERE token_hash = ?",
            (t_hash,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    @_db_locked
    def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a specific user."""
        cur = self._conn.execute(
            "UPDATE user_sessions SET revoked = 1 WHERE user_id = ?",
            (user_id,),
        )
        self._conn.commit()
        return cur.rowcount

    @_db_locked
    def get_user(self, user_id: str) -> Optional[User]:
        row = self._conn.execute(
            "SELECT id, username, role, created_at, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return User(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
        )

    @_db_locked
    def get_user_by_username(self, username: str) -> Optional[User]:
        uname = (username or "").strip().lower()
        row = self._conn.execute(
            "SELECT id, username, role, created_at, is_active FROM users WHERE username = ?",
            (uname,),
        ).fetchone()
        if not row:
            return None
        return User(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
        )

    @_db_locked
    def list_users(self) -> List[User]:
        rows = self._conn.execute(
            "SELECT id, username, role, created_at, is_active FROM users ORDER BY created_at ASC"
        ).fetchall()
        return [
            User(
                id=r["id"],
                username=r["username"],
                role=r["role"],
                created_at=r["created_at"],
                is_active=bool(r["is_active"]),
            )
            for r in rows
        ]

    @_db_locked
    def delete_user(self, user_id: str) -> bool:
        """Delete user account and all cascading sessions and preferences."""
        cur = self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self._conn.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
        self._conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
        self._conn.commit()
        self._record_audit_unlocked("user_deleted", user_id)
        return cur.rowcount > 0

    # ---------------- Per-User Preferences ----------------

    @_db_locked
    def set_preference(self, user_id: str, key: str, value: str) -> None:
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO user_preferences (user_id, key, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (user_id, key, value, now),
        )
        self._conn.commit()

    @_db_locked
    def get_preference(
        self, user_id: str, key: str, default: Optional[str] = None
    ) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM user_preferences WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
        if row:
            return row["value"]
        return default

    @_db_locked
    def get_all_preferences(self, user_id: str) -> Dict[str, str]:
        rows = self._conn.execute(
            "SELECT key, value FROM user_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ---------------- Audit ----------------

    def _record_audit_unlocked(
        self,
        event: str,
        user_id: str,
        ip: str = "",
        details: str = "",
    ) -> None:
        try:
            self._conn.execute(
                """
                INSERT INTO auth_audit_log (timestamp, event, user_id, ip, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (time.time(), event, user_id, ip, details),
            )
            self._conn.commit()
        except Exception:
            pass

    @_db_locked
    def record_audit(
        self, event: str, user_id: str, ip: str = "", details: str = ""
    ) -> None:
        self._record_audit_unlocked(event, user_id, ip, details)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass


_DEFAULT_USER_MANAGER: Optional[UserManager] = None
_MGR_LOCK = threading.Lock()


def get_user_manager() -> UserManager:
    """Return singleton UserManager instance."""
    global _DEFAULT_USER_MANAGER
    with _MGR_LOCK:
        if _DEFAULT_USER_MANAGER is None:
            _DEFAULT_USER_MANAGER = UserManager()
        return _DEFAULT_USER_MANAGER


def set_user_manager(manager: Optional[UserManager]) -> None:
    """Set or reset singleton UserManager (useful for tests)."""
    global _DEFAULT_USER_MANAGER
    with _MGR_LOCK:
        if _DEFAULT_USER_MANAGER is not None and _DEFAULT_USER_MANAGER is not manager:
            try:
                _DEFAULT_USER_MANAGER.close()
            except Exception:
                pass
        _DEFAULT_USER_MANAGER = manager
