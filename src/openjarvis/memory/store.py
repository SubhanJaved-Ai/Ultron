"""Persistent stores for automatically extracted long-term memory facts.

A *fact* is a short, durable statement worth remembering about the user
(e.g. ``"Prefers concise answers"``).  Facts are produced by the memory
service's background extractor and persisted here so they survive across
sessions.  The store is intentionally small and self-contained: it dedupes,
caps the total number of facts, and is safe to call from multiple threads.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from openjarvis.core.paths import get_config_dir
from openjarvis.core.registry import FactStoreRegistry

if sys.platform != "win32":
    import fcntl


_WINDOWS_LOCK_RETRY_SECONDS = 0.01
_WINDOWS_LOCK_RETRY_ERRNOS = {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
_WINDOWS_LOCK_RETRY_WINERRORS = {33}  # ERROR_LOCK_VIOLATION


def _lock_windows_blocking(
    file_obj: Any,
    *,
    locking_api: Any | None = None,
    retry_interval: float = _WINDOWS_LOCK_RETRY_SECONDS,
) -> None:
    """Acquire the first-byte Windows lock, retrying until it is available.

    ``msvcrt.LK_LOCK`` only retries a fixed number of times before raising.
    Use the non-blocking operation in our own retry loop so contention never
    turns an otherwise valid store operation into a spurious failure.
    """
    if locking_api is None:
        import msvcrt as locking_api

    while True:
        file_obj.seek(0)
        try:
            locking_api.locking(file_obj.fileno(), locking_api.LK_NBLCK, 1)
            return
        except OSError as exc:
            if (
                exc.errno not in _WINDOWS_LOCK_RETRY_ERRNOS
                and getattr(exc, "winerror", None) not in _WINDOWS_LOCK_RETRY_WINERRORS
            ):
                raise
            time.sleep(retry_interval)


def _unlock_windows(file_obj: Any, *, locking_api: Any | None = None) -> None:
    if locking_api is None:
        import msvcrt as locking_api

    file_obj.seek(0)
    locking_api.locking(file_obj.fileno(), locking_api.LK_UNLCK, 1)


def _default_fact_path() -> Path:
    """Return the env-aware default JSONL path for automatic memory facts."""
    return get_config_dir() / "memory_facts.jsonl"


# Provenance tiers, recorded on every fact.
TRUST_AUTO = "auto"  # auto-extracted and scanner-clean → recallable
TRUST_TRUSTED = "trusted"  # explicitly vouched for by the user
TRUST_UNTRUSTED = "untrusted"  # scanner flagged the text → quarantined

# Memory categories supported across the system
MEMORY_CATEGORIES = frozenset({
    "general",
    "user_preferences",
    "architecture_decisions",
    "project_context",
    "successful_workflows",
    "recurring_failure_lessons",
})

# Patterns for sanitizing sensitive credentials, tokens, and safety codes
_SENSITIVE_PATTERNS = [
    # Anthropic API keys (sk-ant-...)
    (re.compile(r"sk-ant-[a-zA-Z0-9_\-]{30,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    # OpenAI & OpenJarvis API keys
    (re.compile(r"(?:sk-|oj_sk_)[a-zA-Z0-9_-]{20,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    # Google AI Studio / Gemini / Maps API keys (AIza...)
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"), "[REDACTED_GOOGLE_API_KEY]"),
    # GitHub personal access tokens
    (re.compile(r"gh[pousr]_[a-zA-Z0-9]{36,}", re.IGNORECASE), "[REDACTED_GITHUB_TOKEN]"),
    # Slack tokens (xoxb-, xoxp-, xoxa-, xoxr-, xoxs-)
    (re.compile(r"\bxox[baprs]-[0-9a-zA-Z-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    # Hugging Face tokens (hf_...)
    (re.compile(r"\bhf_[a-zA-Z0-9]{34,}\b"), "[REDACTED_HUGGINGFACE_TOKEN]"),
    # Stripe keys (sk_live_, pk_live_, sk_test_, pk_test_)
    (re.compile(r"\b(?:sk|pk)_(?:live|test)_[0-9a-zA-Z]{24,}\b"), "[REDACTED_STRIPE_KEY]"),
    # AWS access key ID
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    # AWS Secret Access Key
    (re.compile(r'(?i)\b(?:aws_secret_access_key|aws_secret_key)\s*[:=]\s*["\']?([A-Za-z0-9/+=]{40})["\']?'), "aws_secret_access_key=[REDACTED_AWS_SECRET]"),
    # Private Key blocks
    (re.compile(r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----[\s\S]+?-----END (?:[A-Z0-9_-]+ )?PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    # JWT tokens
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT_TOKEN]"),
    # Generic Bearer tokens
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9_.\-~+/]{20,}={0,2}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    # Database connection URIs with password
    (re.compile(r"([a-zA-Z0-9+]+://[^:@\s]+:)([^@\s]+)(@[^/\s]+)"), r"\1****\3"),
    # Passwords or secrets in key-value pairs
    (re.compile(r'(?i)\b(password|passwd|secret|api_key|access_token|private_key|auth_token|client_secret)\s*[:=]\s*["\']?([^"\'\s,;]+)["\']?'), r'\1=[REDACTED]'),
    # Safety codes / verification PINs
    (re.compile(r'(?i)\b(safety[-_ ]?code|verification[-_ ]?pin|auth[-_ ]?code)\s*(?:[:=]|is)?\s*["\']?([0-9]{4,8})["\']?'), r'\1=[REDACTED_SAFETY_CODE]'),
    # Ultron Action Tokens
    (re.compile(r"\bsat_[a-f0-9]{32,}\b"), "[REDACTED_ACTION_TOKEN]"),
]


def scrub_sensitive_data(text: str) -> str:
    """Scrub sensitive credentials, safety codes, access tokens, and passwords from text."""
    if not text:
        return ""
    result = text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def scrub_metadata(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recursively scrub sensitive credential tokens from metadata dictionaries."""
    if not meta:
        return {}
    cleaned: Dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, str):
            cleaned[k] = scrub_sensitive_data(v)
        elif isinstance(v, dict):
            cleaned[k] = scrub_metadata(v)
        elif isinstance(v, list):
            cleaned[k] = [
                scrub_sensitive_data(x) if isinstance(x, str)
                else (scrub_metadata(x) if isinstance(x, dict) else x)
                for x in v
            ]
        else:
            cleaned[k] = v
    return cleaned


_ROLE_DELIMITER_PATTERNS = [
    (re.compile(r"<\|(?:im_start|im_end|system|user|assistant)\|>", re.IGNORECASE), "[ESCAPED_DELIMITER]"),
    (re.compile(r"```\s*(?:system|assistant|prompt|instruction)\b", re.IGNORECASE), "```[safe_ref]"),
]


def sanitize_memory_for_display(text: str) -> str:
    """Neutralize role delimiters and prompt escape sequences in retrieved text."""
    if not text:
        return ""
    result = text
    for pattern, replacement in _ROLE_DELIMITER_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


UNTRUSTED_SOURCE_TYPES = frozenset({
    "website",
    "web",
    "web_search",
    "url",
    "file",
    "file_read",
    "email",
    "tool_output",
    "external",
    "untrusted",
})


def infer_source_type(source: str = "", metadata: Optional[Dict[str, Any]] = None) -> str:
    """Infer provenance source type from source string and metadata."""
    if metadata and metadata.get("source_type"):
        return str(metadata["source_type"]).strip().lower()
    s = (source or "").strip().lower()
    if s.startswith("http://") or s.startswith("https://") or "web" in s or "url" in s:
        return "website"
    if s.startswith("file://") or "/" in s or "\\" in s or s.endswith((".py", ".txt", ".md", ".json", ".html", ".log")):
        return "file"
    if "email" in s or "@" in s:
        return "email"
    if s.startswith("task:"):
        return "task_execution"
    if s in ("user", "user_direct"):
        return "user_direct"
    if "tool" in s:
        return "tool_output"
    return "unknown"


# "" is the legacy on-disk value, written before provenance existed. It stays
# recallable so upgrading does not silently erase a user's existing memory.
# Exported because the same tier vocabulary gates document recall in
# tools.storage.context — a second, drifting copy of this set would be a
# security bug waiting to happen.
RECALLABLE_TRUST_TIERS = frozenset({"", TRUST_AUTO, TRUST_TRUSTED})
_RECALLABLE_TIERS = RECALLABLE_TRUST_TIERS  # internal alias
_PATH_LOCKS: dict[str, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _get_path_lock(path: Path) -> threading.Lock:
    resolved = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        if resolved not in _PATH_LOCKS:
            _PATH_LOCKS[resolved] = threading.Lock()
        return _PATH_LOCKS[resolved]


@contextmanager
def _cross_process_lock(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive, blocking lock on *lock_path*.

    Acquires both an in-process thread lock (to serialize separate instances
    within the same process) and an OS-level file lock (to serialize across
    processes).
    """
    thread_lock = _get_path_lock(lock_path)
    with thread_lock:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(lock_path, "a+b")
        try:
            if sys.platform == "win32":
                # msvcrt locks a byte range; the file needs at least one byte
                # for the region at offset 0 to be lockable.
                f.seek(0, os.SEEK_END)
                if f.tell() == 0:
                    f.write(b"\0")
                    f.flush()
                _lock_windows_blocking(f)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if sys.platform == "win32":
                    _unlock_windows(f)
                else:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()


@dataclass(slots=True)
class Fact:
    """A single durable memory entry."""

    text: str
    source: str = ""
    created_at: float = 0.0
    # Provenance tier: one of the TRUST_* constants above ("" for legacy rows).
    trust: str = ""
    id: str = ""
    category: str = "general"
    project: str = "default"
    updated_at: float = 0.0
    verified: bool = False
    source_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            h = hashlib.sha256(
                f"{self.project}:{self.category}:{self.text}".encode("utf-8")
            ).hexdigest()[:16]
            object.__setattr__(self, "id", f"mem_{h}")
        if not self.updated_at and self.created_at:
            object.__setattr__(self, "updated_at", self.created_at)
        if not self.source_type:
            object.__setattr__(self, "source_type", infer_source_type(self.source, self.metadata))

    @property
    def trusted_for_recall(self) -> bool:
        """Whether this fact may be placed in model-facing context.

        Only ``untrusted`` — the tier the memory service assigns when the
        injection scanner flags a fact's own text — is withheld. Unknown
        future tiers fail closed rather than silently becoming prompt input.
        """
        return (self.trust or "").strip().lower() in _RECALLABLE_TIERS

    @property
    def resolved_source_type(self) -> str:
        """Normalized source type (website, file, email, tool_output, task_execution, user_direct)."""
        return self.source_type or infer_source_type(self.source, self.metadata)

    @property
    def is_external_untrusted_source(self) -> bool:
        """Whether this fact originated from an external untrusted source."""
        return self.resolved_source_type in UNTRUSTED_SOURCE_TYPES

    def to_dict(self) -> Dict[str, Any]:
        """Serialize memory fact to dictionary for JSON APIs and representations."""
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "source_type": self.resolved_source_type,
            "is_external_untrusted_source": self.is_external_untrusted_source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "trust": self.trust,
            "trusted_for_recall": self.trusted_for_recall,
            "category": self.category,
            "project": self.project,
            "verified": self.verified,
            "metadata": dict(self.metadata or {}),
        }


class FactStore(ABC):
    """Abstract persistent store for extracted memory facts."""

    @abstractmethod
    def add(
        self,
        text: str,
        source: str = "",
        trust: str = "",
        category: str = "general",
        project: str = "default",
        verified: bool = False,
        source_type: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: str = "",
    ) -> bool:
        """Store *text* as a fact. Returns True if a new fact was stored."""

    def set_trust(self, index: int, trust: str) -> bool:
        """Set the provenance tier of the *index*-th fact (0-based) as returned
        by :meth:`list`. Returns True if a fact was updated."""
        raise NotImplementedError

    def add_many(self, texts: Iterable[str], source: str = "") -> int:
        """Store several facts, returning the count of newly stored ones."""
        added = 0
        for text in texts:
            if self.add(text, source=source):
                added += 1
        return added

    def add_with_trust(self, text: str, source: str = "", trust: str = "") -> bool:
        """Store a provenance-aware fact without breaking legacy backends.

        Third-party stores implementing the original ``add(text, source)``
        contract inherit this adapter. Recallable facts are stored normally;
        quarantined or unknown tiers are dropped because a backend that cannot
        persist provenance cannot safely retain them for model-facing recall.
        Provenance-aware stores should override this method.
        """
        if (trust or "").strip().lower() not in _RECALLABLE_TIERS:
            return False
        return self.add(text, source=source)

    def add_many_with_trust(
        self,
        texts: Iterable[str],
        source: str = "",
        trust: str = "",
    ) -> int:
        """Store several provenance-aware facts."""
        return sum(
            bool(self.add_with_trust(text, source=source, trust=trust))
            for text in texts
        )

    def promote_reviewed(self, index: int, expected_text: str) -> bool:
        """Promote the reviewed fact at *index* when it still matches.

        The default preserves compatibility with third-party implementations;
        stores with concurrent writers should override this with an atomic
        identity check.
        """
        del expected_text
        return self.set_trust(index, TRUST_TRUSTED)

    def get(self, memory_id: str) -> Optional[Fact]:
        """Retrieve a memory entry by ID."""
        raise NotImplementedError

    def update(
        self,
        memory_id: str,
        *,
        text: Optional[str] = None,
        category: Optional[str] = None,
        project: Optional[str] = None,
        trust: Optional[str] = None,
        verified: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update an existing memory entry."""
        raise NotImplementedError

    def delete(self, memory_id: str) -> bool:
        """Delete a memory entry by ID."""
        raise NotImplementedError

    def query(
        self,
        *,
        project: Optional[str] = None,
        category: Optional[str] = None,
        query: Optional[str] = None,
        verified_only: bool = False,
        recallable_only: bool = True,
        limit: Optional[int] = None,
    ) -> List[Fact]:
        """Query stored memories with filters and search."""
        raise NotImplementedError

    @abstractmethod
    def list(self) -> List[Fact]:
        """Return all stored facts, oldest first."""

    @abstractmethod
    def clear(self) -> int:
        """Remove all stored facts, returning the number removed."""

    @abstractmethod
    def count(self) -> int:
        """Return the number of stored facts."""


@FactStoreRegistry.register("local")
class LocalFactStore(FactStore):
    """Append-only JSONL fact store on the local filesystem.

    Facts are kept human-readable (one JSON object per line) so they can be
    inspected or edited by hand.  Writes are atomic (temp file + rename) and
    guarded by a lock, so concurrent ``add`` calls from the extraction worker
    and ``list``/``clear`` from the CLI never corrupt the file.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        max_facts: int = 1000,
    ) -> None:
        max_facts = int(max_facts)
        if max_facts <= 0:
            raise ValueError(f"max_facts must be a positive integer, got {max_facts}")
        self._path = (
            Path(path).expanduser() if path is not None else _default_fact_path()
        )
        self._max_facts = max_facts
        self._lock = threading.Lock()
        self._facts: List[Fact] = self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> List[Fact]:
        if not self._path.exists():
            return []
        facts: List[Fact] = []
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue  # skip malformed lines rather than crashing
            fact_text = str(obj.get("text", "")).strip()
            if not fact_text:
                continue
            facts.append(
                Fact(
                    text=fact_text,
                    source=str(obj.get("source", "")),
                    created_at=float(obj.get("created_at", 0.0) or 0.0),
                    trust=str(obj.get("trust", "")),
                    id=str(obj.get("id", "") or ""),
                    category=str(obj.get("category", "general")),
                    project=str(obj.get("project", "default")),
                    updated_at=float(obj.get("updated_at", 0.0) or 0.0),
                    verified=bool(obj.get("verified", False)),
                    source_type=str(obj.get("source_type", "") or ""),
                    metadata=dict(obj.get("metadata", {}) or {}),
                )
            )
        return facts

    def _flush(self) -> None:
        """Atomically rewrite the JSONL file from the in-memory list."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(
            json.dumps(asdict(f), ensure_ascii=False) + "\n" for f in self._facts
        )
        # A fixed temp filename lets two concurrent writers interleave into
        # the same temp file before either os.replace() runs (#755); a
        # unique name per flush avoids that collision entirely.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self._path.parent),
            prefix=self._path.name + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
                tmp_f.write(payload)
            for attempt in range(10):
                try:
                    os.replace(tmp_name, self._path)
                    break
                except PermissionError:
                    if attempt == 9 or sys.platform != "win32":
                        raise
                    time.sleep(0.02)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _lock_path(self) -> Path:
        return self._path.with_suffix(self._path.suffix + ".lock")

    def _sync_from_disk_locked(self) -> None:
        """Refresh in-memory facts from disk while holding ``self._lock``."""
        self._facts = self._load()

    # -- FactStore API ------------------------------------------------------

    def add(
        self,
        text: str,
        source: str = "",
        trust: str = "",
        category: str = "general",
        project: str = "default",
        verified: bool = False,
        source_type: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: str = "",
    ) -> bool:
        raw = (text or "").strip()
        if not raw:
            return False
        clean_text = scrub_sensitive_data(raw).strip()
        if not clean_text:
            return False
        clean_meta = scrub_metadata(metadata)
        trust = (trust or "").strip().lower()
        cat = (category or "general").strip().lower()
        proj = (project or "default").strip()
        s_type = (source_type or "").strip().lower() or infer_source_type(source, clean_meta)
        clean_meta["source_type"] = s_type

        # Provenance: If originating from external untrusted content, mark it
        if s_type in UNTRUSTED_SOURCE_TYPES:
            clean_meta["is_untrusted_source"] = True
            if not trust:
                trust = TRUST_AUTO

        # Prompt Injection & Directive Detection:
        # Treat untrusted instructions/injections as unrecallable data (quarantined)
        try:
            from openjarvis.security.injection_scanner import InjectionScanner

            _scanner = InjectionScanner()
            _scan_res = _scanner.scan(clean_text)
            if _scan_res and not _scan_res.is_clean:
                trust = TRUST_UNTRUSTED
                clean_meta["quarantined"] = True
                findings = [f.pattern_name for f in getattr(_scan_res, "findings", [])]
                clean_meta["quarantine_reason"] = f"Prompt injection/instruction detected: {findings}"
        except Exception as exc:
            logger.debug("Injection scanner in fact store error: %s", exc)

        now = time.time()

        with self._lock, _cross_process_lock(self._lock_path()):
            self._sync_from_disk_locked()
            lowered = clean_text.lower()
            duplicate = next(
                (
                    fact for fact in self._facts
                    if fact.text.lower() == lowered
                    and fact.project.lower() == proj.lower()
                    and fact.category.lower() == cat
                ),
                None,
            )
            if duplicate is not None:
                # A later hostile derivation must be able to quarantine an
                # older recallable copy. Never auto-promote in the opposite
                # direction; promotion requires explicit human review.
                if trust not in _RECALLABLE_TIERS and duplicate.trusted_for_recall:
                    duplicate.trust = trust or TRUST_UNTRUSTED
                    self._flush()
                return False  # dedupe
            self._facts.append(
                Fact(
                    text=clean_text,
                    source=source,
                    created_at=now,
                    trust=trust,
                    id=memory_id or "",
                    category=cat,
                    project=proj,
                    updated_at=now,
                    verified=verified,
                    source_type=s_type,
                    metadata=clean_meta,
                )
            )
            # Enforce the cap by evicting the oldest entries. max_facts is
            # always positive (validated in __init__), so this slice can't
            # hit Python's `list[-0:]` footgun, which returns the whole
            # list instead of emptying it.
            if len(self._facts) > self._max_facts:
                self._facts = self._facts[-self._max_facts :]
            self._flush()
        return True

    def get(self, memory_id: str) -> Optional[Fact]:
        with self._lock:
            self._sync_from_disk_locked()
            for fact in self._facts:
                if fact.id == memory_id:
                    return fact
        return None

    def update(
        self,
        memory_id: str,
        *,
        text: Optional[str] = None,
        category: Optional[str] = None,
        project: Optional[str] = None,
        trust: Optional[str] = None,
        verified: Optional[bool] = None,
        source_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        with self._lock, _cross_process_lock(self._lock_path()):
            self._sync_from_disk_locked()
            for fact in self._facts:
                if fact.id == memory_id:
                    now = time.time()
                    if text is not None:
                        clean_text = scrub_sensitive_data(text).strip()
                        if not clean_text:
                            return False
                        fact.text = clean_text
                        try:
                            from openjarvis.security.injection_scanner import InjectionScanner

                            _scanner = InjectionScanner()
                            _scan_res = _scanner.scan(clean_text)
                            if _scan_res and not _scan_res.is_clean:
                                fact.trust = TRUST_UNTRUSTED
                                fact.metadata["quarantined"] = True
                                findings = [f.pattern_name for f in getattr(_scan_res, "findings", [])]
                                fact.metadata["quarantine_reason"] = f"Prompt injection detected on update: {findings}"
                        except Exception:
                            pass
                    if category is not None:
                        fact.category = category.strip().lower()
                    if project is not None:
                        fact.project = project.strip()
                    if trust is not None:
                        fact.trust = trust.strip().lower()
                    if verified is not None:
                        fact.verified = verified
                    if source_type is not None:
                        fact.source_type = source_type.strip().lower()
                    if metadata is not None:
                        fact.metadata = scrub_metadata(dict(metadata))
                    fact.updated_at = now
                    self._flush()
                    return True
        return False

    def delete(self, memory_id: str) -> bool:
        with self._lock, _cross_process_lock(self._lock_path()):
            self._sync_from_disk_locked()
            initial_count = len(self._facts)
            self._facts = [f for f in self._facts if f.id != memory_id]
            if len(self._facts) < initial_count:
                self._flush()
                return True
        return False

    def query(
        self,
        *,
        project: Optional[str] = None,
        category: Optional[str] = None,
        query: Optional[str] = None,
        verified_only: bool = False,
        recallable_only: bool = True,
        source_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Fact]:
        with self._lock:
            self._sync_from_disk_locked()
            results = list(self._facts)

        if recallable_only:
            results = [f for f in results if f.trusted_for_recall]

        if verified_only:
            results = [f for f in results if f.verified]

        if source_type is not None:
            s_low = source_type.strip().lower()
            results = [f for f in results if f.resolved_source_type.lower() == s_low]

        if project is not None and project != "*":
            proj_low = project.strip().lower()
            results = [f for f in results if f.project.lower() == proj_low or f.project == "default"]

        if category is not None and category != "*":
            cat_low = category.strip().lower()
            results = [f for f in results if f.category.lower() == cat_low]

        if query:
            tokens = [t.lower() for t in query.split() if len(t) > 2]
            if tokens:
                def score(f: Fact) -> int:
                    text_low = f.text.lower()
                    return sum(1 for t in tokens if t in text_low)
                results = [f for f in results if score(f) > 0]
                results.sort(key=score, reverse=True)

        if limit is not None and limit > 0:
            results = results[:limit]

        return results

    def add_with_trust(self, text: str, source: str = "", trust: str = "") -> bool:
        return self.add(text, source=source, trust=trust)

    def set_trust(self, index: int, trust: str) -> bool:
        trust = (trust or "").strip().lower()
        if trust not in {TRUST_AUTO, TRUST_TRUSTED, TRUST_UNTRUSTED}:
            raise ValueError(f"Unknown fact trust tier: {trust!r}")
        with self._lock, _cross_process_lock(self._lock_path()):
            self._sync_from_disk_locked()
            if not 0 <= index < len(self._facts):
                return False
            self._facts[index].trust = trust
            self._flush()
        return True

    def promote_reviewed(self, index: int, expected_text: str) -> bool:
        """Atomically promote exactly the fact a user reviewed."""
        with self._lock, _cross_process_lock(self._lock_path()):
            self._sync_from_disk_locked()
            if not 0 <= index < len(self._facts):
                return False
            fact = self._facts[index]
            if fact.text != expected_text or fact.trusted_for_recall:
                return False
            fact.trust = TRUST_TRUSTED
            self._flush()
        return True

    def list(self) -> List[Fact]:
        with self._lock:
            self._sync_from_disk_locked()
            return list(self._facts)

    def clear(self) -> int:
        with self._lock, _cross_process_lock(self._lock_path()):
            self._sync_from_disk_locked()
            removed = len(self._facts)
            self._facts = []
            if self._path.exists():
                try:
                    self._path.unlink()
                except OSError:
                    self._flush()
        return removed

    def count(self) -> int:
        with self._lock:
            self._sync_from_disk_locked()
            return len(self._facts)

    @property
    def path(self) -> Path:
        """Filesystem location of the JSONL store."""
        return self._path


def _ensure_fact_store_backends_registered() -> None:
    """Restore built-in fact-store registrations if a test cleared registries."""
    if not FactStoreRegistry.contains("local"):
        FactStoreRegistry.register_value("local", LocalFactStore)


def create_fact_store(
    backend: str = "local",
    *,
    path: str | Path | None = None,
    max_facts: int = 1000,
) -> FactStore:
    """Construct a fact store for the configured *backend*.

    Only the ``"local"`` (on-disk JSONL) backend is supported today; the
    registry-backed constructor exists so additional backends can be added
    without changing the service or CLI wiring.
    """
    _ensure_fact_store_backends_registered()
    key = (backend or "local").strip().lower()
    if not FactStoreRegistry.contains(key):
        supported = ", ".join(FactStoreRegistry.keys())
        raise ValueError(
            f"Unknown memory backend '{backend}'. Supported backends: {supported}"
        )
    return FactStoreRegistry.create(key, path, max_facts=max_facts)


def load_configured_facts(config: Any) -> List[Fact]:
    """Load automatic-memory facts from *config* when the service is enabled.

    Context injection is also used by short-lived commands such as
    ``jarvis ask``, where no :class:`MemoryService` instance exists.  This
    helper gives those callers the same configured fact-store view without
    coupling them to the service lifecycle.
    """
    memory = getattr(config, "memory", None)
    if memory is None or not getattr(memory, "enabled", False):
        return []

    store = create_fact_store(
        getattr(memory, "backend", "local"),
        path=getattr(memory, "facts_path", None),
        max_facts=getattr(memory, "max_facts", 1000),
    )
    # This helper feeds short-lived model paths (ask, SDK, system
    # orchestrator). Keep the full list available through FactStore.list() for
    # auditing/CLI use, but never return quarantined facts for model recall.
    return [fact for fact in store.list() if fact.trusted_for_recall]


__all__ = [
    "MEMORY_CATEGORIES",
    "RECALLABLE_TRUST_TIERS",
    "TRUST_AUTO",
    "TRUST_TRUSTED",
    "TRUST_UNTRUSTED",
    "UNTRUSTED_SOURCE_TYPES",
    "Fact",
    "FactStore",
    "LocalFactStore",
    "create_fact_store",
    "infer_source_type",
    "load_configured_facts",
    "sanitize_memory_for_display",
    "scrub_metadata",
    "scrub_sensitive_data",
]
