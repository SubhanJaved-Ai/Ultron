"""Skill mutation audit ledger and content-addressed rollback engine.

Inspired by Hermes Agent's skill ledger: every skill mutation (create, patch,
delete, rollback) appends a durable audit record to ``.skill_ledger.jsonl``
with content-addressed (sha256-deduped) file blob backups under
``.skill_backups/blobs/``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SkillMutationRecord:
    """A durable audit record for a single skill mutation."""

    id: str
    timestamp: float
    action: str  # "create" | "patch" | "delete" | "rollback"
    skill_name: str
    author: str = "agent"
    description: str = ""
    before_manifest: Dict[str, str] = field(default_factory=dict)
    after_manifest: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SkillMutationRecord:
        return cls(
            id=data.get("id", ""),
            timestamp=float(data.get("timestamp", 0.0)),
            action=data.get("action", ""),
            skill_name=data.get("skill_name", ""),
            author=data.get("author", "agent"),
            description=data.get("description", ""),
            before_manifest=data.get("before_manifest", {}) or {},
            after_manifest=data.get("after_manifest", {}) or {},
        )


class SkillLedger:
    """Manages skill mutation history, blob storage, and atomic rollbacks.

    Parameters
    ----------
    skills_dir:
        Root directory containing skill packages.
    ledger_path:
        Optional custom path to the ledger JSONL file.
    blobs_dir:
        Optional custom path to the content-addressed blob directory.
    """

    def __init__(
        self,
        skills_dir: Path | str,
        ledger_path: Optional[Path | str] = None,
        blobs_dir: Optional[Path | str] = None,
    ) -> None:
        self.skills_dir = Path(skills_dir).expanduser()
        self.ledger_path = (
            Path(ledger_path).expanduser()
            if ledger_path
            else self.skills_dir / ".skill_ledger.jsonl"
        )
        self.blobs_dir = (
            Path(blobs_dir).expanduser()
            if blobs_dir
            else self.skills_dir / ".skill_backups" / "blobs"
        )
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.blobs_dir.mkdir(parents=True, exist_ok=True)

    def _hash_file(self, path: Path) -> str:
        """Compute sha256 checksum of a file."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _store_blob(self, file_path: Path) -> str:
        """Copy a file to content-addressed storage keyed by its sha256."""
        sha = self._hash_file(file_path)
        blob_path = self.blobs_dir / sha
        if not blob_path.exists():
            temp_path = self.blobs_dir / f".tmp_{uuid.uuid4().hex}"
            shutil.copy2(file_path, temp_path)
            temp_path.replace(blob_path)
        return sha

    def capture_snapshot(self, skill_dir: Path) -> Dict[str, str]:
        """Capture a content-addressed snapshot of a skill directory.

        Returns a manifest mapping relative POSIX paths to their sha256 checksums.
        """
        manifest: Dict[str, str] = {}
        if not skill_dir.exists() or not skill_dir.is_dir():
            return manifest

        for root, dirs, files in os.walk(skill_dir):
            # Exclude hidden files and backups
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for file_name in files:
                if file_name.startswith("."):
                    continue
                full_path = Path(root) / file_name
                rel_path = full_path.relative_to(skill_dir).as_posix()
                sha = self._store_blob(full_path)
                manifest[rel_path] = sha

        return manifest

    def record_mutation(
        self,
        skill_name: str,
        action: str,
        before_manifest: Dict[str, str],
        after_manifest: Dict[str, str],
        description: str = "",
        author: str = "agent",
    ) -> SkillMutationRecord:
        """Append a mutation entry to the JSONL ledger."""
        record = SkillMutationRecord(
            id=uuid.uuid4().hex[:16],
            timestamp=time.time(),
            action=action,
            skill_name=skill_name,
            author=author,
            description=description,
            before_manifest=before_manifest,
            after_manifest=after_manifest,
        )
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")
        logger.info(
            "Recorded skill mutation %s for '%s' (%s)",
            record.id,
            skill_name,
            action,
        )
        return record

    def get_history(
        self,
        skill_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[SkillMutationRecord]:
        """Retrieve historical mutation entries in reverse chronological order."""
        if not self.ledger_path.exists():
            return []

        records: List[SkillMutationRecord] = []
        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = SkillMutationRecord.from_dict(json.loads(line))
                        if skill_name is None or rec.skill_name == skill_name:
                            records.append(rec)
                    except Exception:
                        continue
        except Exception as e:
            logger.warning("Error reading skill ledger %s: %s", self.ledger_path, e)

        records.reverse()
        return records[:limit]

    def get_record(self, entry_id: str) -> Optional[SkillMutationRecord]:
        """Fetch a specific mutation record by ID."""
        for rec in self.get_history(limit=500):
            if rec.id == entry_id:
                return rec
        return None

    def rollback_entry(
        self,
        entry_id: str,
        target_dir: Optional[Path] = None,
    ) -> bool:
        """Rollback a specific mutation by restoring its before_manifest state."""
        rec = self.get_record(entry_id)
        if rec is None:
            logger.error("Ledger entry %s not found for rollback", entry_id)
            return False

        if target_dir is not None:
            skill_dir = target_dir
        elif (self.skills_dir / rec.skill_name).is_dir():
            skill_dir = self.skills_dir / rec.skill_name
        else:
            skill_dir = self.skills_dir

        before_manifest = rec.before_manifest
        after_manifest = rec.after_manifest

        # Snapshot current state before rolling back
        current_snapshot = self.capture_snapshot(skill_dir)

        if not before_manifest:
            # The mutation created the skill, so rollback deletes it
            if skill_dir.exists():
                shutil.rmtree(skill_dir, ignore_errors=True)
            self.record_mutation(
                skill_name=rec.skill_name,
                action="rollback",
                before_manifest=current_snapshot,
                after_manifest={},
                description=f"Rollback mutation {entry_id} (reverted creation)",
            )
            return True

        # Otherwise restore all files from before_manifest
        skill_dir.mkdir(parents=True, exist_ok=True)

        # 1. Restore files from blobs
        for rel_path, sha in before_manifest.items():
            blob_path = self.blobs_dir / sha
            if not blob_path.exists():
                logger.error("Missing blob %s for %s", sha, rel_path)
                return False
            dest_file = skill_dir / Path(rel_path)
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(blob_path, dest_file)

        # 2. Delete any files introduced in after_manifest that were not in before_manifest
        for rel_path in after_manifest.keys():
            if rel_path not in before_manifest:
                file_to_remove = skill_dir / Path(rel_path)
                if file_to_remove.exists():
                    try:
                        file_to_remove.unlink()
                    except Exception:
                        pass

        # Capture post-rollback snapshot
        post_snapshot = self.capture_snapshot(skill_dir)
        self.record_mutation(
            skill_name=rec.skill_name,
            action="rollback",
            before_manifest=current_snapshot,
            after_manifest=post_snapshot,
            description=f"Rollback mutation {entry_id}",
        )
        return True

    def rollback_latest(
        self,
        skill_name: str,
        target_dir: Optional[Path] = None,
    ) -> bool:
        """Find the latest non-rollback mutation for this skill and revert it."""
        history = self.get_history(skill_name=skill_name, limit=20)
        # Find first non-rollback mutation
        for rec in history:
            if rec.action in ("patch", "create", "delete"):
                return self.rollback_entry(rec.id, target_dir=target_dir)
        logger.warning("No eligible mutation found to rollback for %s", skill_name)
        return False
