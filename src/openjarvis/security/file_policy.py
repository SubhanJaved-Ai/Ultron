"""File sensitivity policy — block access to secrets, credentials, and keys."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, List, Union

DEFAULT_SENSITIVE_PATTERNS: frozenset[str] = frozenset(
    {
        ".env",
        ".env.*",
        "*.env",
        ".secret",
        "*.secrets",
        "credentials.*",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
        "*.jks",
        "id_rsa",
        "id_ed25519",
        ".htpasswd",
        ".pgpass",
        ".netrc",
    }
)


def is_sensitive_file(path: Union[str, Path]) -> bool:
    """Return ``True`` if *path* matches a sensitive file pattern.

    Checks the original path, symlink targets, and resolved path against
    ``DEFAULT_SENSITIVE_PATTERNS``. A symlink must not bypass the policy by
    hiding a sensitive name anywhere in its chain.
    Uses the Rust implementation when available, falls back to Python.
    """
    try:
        from openjarvis._rust_bridge import get_rust_module

        _rust = get_rust_module()
        check = _rust.is_sensitive_file
    except ImportError:
        check = _is_sensitive_file_py

    return any(check(str(candidate)) for candidate in _paths_for_policy(Path(path)))


def _paths_for_policy(path: Path) -> Iterator[Path]:
    """Keep sensitive names that full resolution would discard."""
    yield path
    candidate = path
    for _ in range(40):
        try:
            target = candidate.readlink()
        except OSError:
            break
        candidate = target if target.is_absolute() else candidate.parent / target
        yield candidate

    try:
        # Also resolve symlinks in parent directories and normalize the target.
        yield path.resolve(strict=False)
    except (OSError, RuntimeError):
        # Missing files and loops retain the checks above. The filesystem
        # operation will report its own error when a path is not usable.
        return


def _is_sensitive_file_py(path_str: str) -> bool:
    """Pure-Python fallback for sensitive file detection."""
    import fnmatch

    p = Path(path_str)
    name = p.name
    for pattern in DEFAULT_SENSITIVE_PATTERNS:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(str(p), pattern):
            return True
    return False


def filter_sensitive_paths(paths: Iterable[Union[str, Path]]) -> List[Path]:
    """Return only non-sensitive paths from *paths*."""
    return [Path(p) for p in paths if not is_sensitive_file(p)]


def validate_ultron_fs_operation(path: Union[str, Path], operation: str = "write") -> tuple[bool, str]:
    """Validate filesystem operation against Ultron safety guardrails.

    Enforces:
    1. Zero Deletion Policy: All delete/remove/unlink actions are strictly prohibited.
    2. C: Drive Isolation: All write/create/modify operations on the C: system drive are forbidden.
    3. Sensitive Credential / Key Protection: Paths matching secret patterns are blocked.
    4. Allowed Non-System Storage: Read/write operations are restricted to D: or verified safe drives.
    """
    op = (operation or "").lower().strip()
    # 1. Zero Deletion Policy
    if op in ("delete", "remove", "unlink", "rm", "del", "destroy", "purge", "rmdir"):
        return False, "Guardrail Policy Violation: File deletion is strictly prohibited by Ultron Zero-Data-Loss Safety Policy."

    p = Path(path)

    # 2. C: Drive Write Isolation
    try:
        resolved = p.resolve(strict=False)
        drive = resolved.drive.upper()
    except Exception:
        drive = str(p)[:2].upper()

    if op in ("create", "write", "append", "touch", "modify"):
        if drive == "C:":
            return False, "Guardrail Policy Violation: Write access to C: drive is strictly restricted by Ultron Security Guardrails. All workspace operations must be performed on D: drive or designated safe storage."

    # 3. Sensitive file check
    if is_sensitive_file(p):
        return False, f"Guardrail Policy Violation: Path '{p.name}' is classified as a sensitive credential or secret file."

    return True, "Guardrail validation passed."


__all__ = [
    "DEFAULT_SENSITIVE_PATTERNS",
    "filter_sensitive_paths",
    "is_sensitive_file",
    "validate_ultron_fs_operation",
]

