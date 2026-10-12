"""Cryptographic utilities for authentication and password hashing.

Uses standard library hashlib with PBKDF2-HMAC-SHA256 (600,000 iterations per OWASP recommendations)
and secrets module for CSPRNG salts and tokens.
Supports transparent zero-downtime hash upgrades and backwards compatibility with legacy hashes.
No external binary dependencies required.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Tuple

_PBKDF2_ITERATIONS = 600_000
_LEGACY_PBKDF2_ITERATIONS = 100_000
_SALT_BYTES = 16
_HASH_NAME = "sha256"


def hash_password(password: str, salt: bytes | None = None) -> Tuple[str, str]:
    """Hash a password using PBKDF2-HMAC-SHA256 (600,000 iterations).

    Returns:
        (formatted_hash, hex_salt)
        formatted_hash is of format: pbkdf2:sha256:600000$<salt_hex>$<hash_hex>
    """
    if salt is None:
        salt = secrets.token_bytes(_SALT_BYTES)
    pwd_bytes = password.encode("utf-8")
    derived = hashlib.pbkdf2_hmac(
        _HASH_NAME,
        pwd_bytes,
        salt,
        _PBKDF2_ITERATIONS,
    )
    formatted = f"pbkdf2:sha256:{_PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"
    return formatted, salt.hex()


def verify_password(password: str, password_hash: str, salt_hex: str = "") -> bool:
    """Verify a password against stored hash in constant time.

    Supports modern formatted strings (pbkdf2:sha256:<iters>$<salt>$<hash>)
    and legacy raw hex hashes with 100,000 iterations.
    """
    if not password or not password_hash:
        return False

    pwd_bytes = password.encode("utf-8")

    try:
        if password_hash.startswith("pbkdf2:sha256:"):
            parts = password_hash.split("$")
            if len(parts) != 3:
                return False
            prefix, s_hex, h_hex = parts
            iters = int(prefix.split(":")[-1])
            salt = bytes.fromhex(s_hex)
            expected_hash = bytes.fromhex(h_hex)
            derived = hashlib.pbkdf2_hmac(_HASH_NAME, pwd_bytes, salt, iters)
            return hmac.compare_digest(derived, expected_hash)
        else:
            # Legacy format: raw hex string
            salt = bytes.fromhex(salt_hex)
            expected_hash = bytes.fromhex(password_hash)
            derived = hashlib.pbkdf2_hmac(
                _HASH_NAME,
                pwd_bytes,
                salt,
                _LEGACY_PBKDF2_ITERATIONS,
            )
            return hmac.compare_digest(derived, expected_hash)
    except (ValueError, TypeError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Check if the stored password hash needs an upgrade to current OWASP standards."""
    target_prefix = f"pbkdf2:sha256:{_PBKDF2_ITERATIONS}$"
    return not password_hash.startswith(target_prefix)


def generate_session_token() -> str:
    """Generate a high-entropy session token with 'oj_usr_' prefix."""
    return f"oj_usr_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    """Hash a session token with SHA-256 for safe storage at rest."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
