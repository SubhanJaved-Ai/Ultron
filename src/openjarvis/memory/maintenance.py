"""Memory Consolidation & Maintenance Engine for Ultron.

Detects memory anomalies across persistent facts:
1. Likely duplicates (exact and high lexical overlap).
2. Contradictory facts (polar opposite directives and conflicting entity/config assignments).
3. Potentially outdated or stale memories (superseded by newer versions or milestones).

Enforces strict human approval (no auto-deletion/merge), project isolation (never compare across
projects), secret scrubbing, prompt-injection quarantine, and quarantine protection
(consolidation can never promote quarantined memories to trusted status).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from openjarvis.core.paths import get_config_dir
from openjarvis.memory.store import (
    Fact,
    FactStore,
    TRUST_AUTO,
    TRUST_TRUSTED,
    TRUST_UNTRUSTED,
    infer_source_type,
    scrub_metadata,
    scrub_sensitive_data,
)
from openjarvis.security.injection_scanner import InjectionScanner

logger = logging.getLogger(__name__)


class MaintenanceIssueType:
    """Types of detected memory issues."""

    DUPLICATE = "duplicate"
    CONTRADICTION = "contradiction"
    OUTDATED = "outdated"


class ProposedAction:
    """Proposed maintenance actions requiring human approval."""

    MERGE = "merge"
    SUPERSEDE = "supersede"
    DELETE = "delete"
    MARK_FOR_REVIEW = "mark_for_review"


class SuggestionStatus:
    """Lifecycle status of a maintenance suggestion."""

    PENDING = "pending"
    APPROVED = "approved"
    DISMISSED = "dismissed"


@dataclass
class MaintenanceSuggestion:
    """A detected maintenance issue with proposed remediation awaiting human review."""

    id: str
    issue_type: str  # "duplicate" | "contradiction" | "outdated"
    project: str
    category: str
    reason: str
    source_fact_ids: List[str]
    source_facts: List[Dict[str, Any]]
    proposed_action: str  # "merge" | "supersede" | "delete" | "mark_for_review"
    proposed_resolution: Dict[str, Any]
    quarantined_involved: bool = False
    status: str = SuggestionStatus.PENDING
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None
    dismiss_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize suggestion to dictionary."""
        return {
            "id": self.id,
            "issue_type": self.issue_type,
            "project": self.project,
            "category": self.category,
            "reason": self.reason,
            "source_fact_ids": list(self.source_fact_ids),
            "source_facts": self.source_facts,
            "proposed_action": self.proposed_action,
            "proposed_resolution": dict(self.proposed_resolution),
            "quarantined_involved": self.quarantined_involved,
            "status": self.status,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "dismiss_reason": self.dismiss_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MaintenanceSuggestion:
        """Instantiate suggestion from dictionary."""
        return cls(
            id=data["id"],
            issue_type=data["issue_type"],
            project=data.get("project", "default"),
            category=data.get("category", "general"),
            reason=data.get("reason", ""),
            source_fact_ids=list(data.get("source_fact_ids", [])),
            source_facts=list(data.get("source_facts", [])),
            proposed_action=data.get("proposed_action", ProposedAction.MARK_FOR_REVIEW),
            proposed_resolution=dict(data.get("proposed_resolution", {})),
            quarantined_involved=bool(data.get("quarantined_involved", False)),
            status=data.get("status", SuggestionStatus.PENDING),
            created_at=data.get("created_at", time.time()),
            resolved_at=data.get("resolved_at"),
            resolved_by=data.get("resolved_by"),
            dismiss_reason=data.get("dismiss_reason"),
        )


def _normalize_tokens(text: str) -> Set[str]:
    """Tokenize and normalize text for lexical comparison."""
    cleaned = re.sub(r"[^\w\s]", " ", (text or "").lower())
    tokens = {t for t in cleaned.split() if len(t) >= 2}
    return tokens


def _jaccard_similarity(tokens1: Set[str], tokens2: Set[str]) -> float:
    """Calculate Jaccard similarity index between two token sets."""
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return intersection / union if union > 0 else 0.0


# Words indicating polarity/direction for contradiction detection
_POSITIVE_INDICATORS = frozenset({
    "always",
    "enable",
    "enabled",
    "prefer",
    "prefers",
    "preferred",
    "use",
    "uses",
    "using",
    "must",
    "require",
    "requires",
    "allow",
    "allows",
    "active",
    "true",
    "on",
    "include",
    "includes",
})

_NEGATIVE_INDICATORS = frozenset({
    "never",
    "disable",
    "disabled",
    "avoid",
    "avoids",
    "dont",
    "do not",
    "cannot",
    "prohibit",
    "prohibits",
    "deny",
    "inactive",
    "false",
    "off",
    "exclude",
    "excludes",
    "without",
    "skip",
    "skips",
})

_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "for", "in", "to", "and",
    "or", "of", "with", "by", "at", "it", "on", "this", "that", "all", "our",
    "my", "we", "be", "been", "as", "from",
})


class MemoryMaintenanceManager:
    """Engine for scanning, reviewing, and approving memory consolidation suggestions."""

    def __init__(
        self,
        fact_store: FactStore,
        suggestions_path: Optional[Path] = None,
    ) -> None:
        self.fact_store = fact_store
        self.suggestions_path = suggestions_path or (get_config_dir() / "memory_maintenance_suggestions.json")
        self._lock = threading.Lock()
        self._suggestions: Dict[str, MaintenanceSuggestion] = {}
        self._load_suggestions()

    # ------------------------------------------------------------------
    # Persistence of Suggestions
    # ------------------------------------------------------------------

    def _load_suggestions(self) -> None:
        """Load cached suggestions from disk if present."""
        if not self.suggestions_path.exists():
            return
        try:
            with open(self.suggestions_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for item in raw:
                try:
                    sug = MaintenanceSuggestion.from_dict(item)
                    self._suggestions[sug.id] = sug
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("Failed to read maintenance suggestions file: %s", exc)

    def _save_suggestions(self) -> None:
        """Persist suggestions to disk."""
        try:
            self.suggestions_path.parent.mkdir(parents=True, exist_ok=True)
            serializable = [sug.to_dict() for sug in self._suggestions.values()]
            tmp = self.suggestions_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
            tmp.replace(self.suggestions_path)
        except Exception as exc:
            logger.debug("Failed to save maintenance suggestions: %s", exc)

    # ------------------------------------------------------------------
    # On-Demand Scanning
    # ------------------------------------------------------------------

    def scan(self, project: Optional[str] = None) -> List[MaintenanceSuggestion]:
        """Perform on-demand scan of memories to detect duplicates, contradictions, and stale items.

        Parameters
        ----------
        project:
            Optional project scope to scan. If omitted, scans all accessible projects.
            Comparisons NEVER cross project boundaries.

        Returns
        -------
        List[MaintenanceSuggestion]:
            List of detected issues awaiting human review.
        """
        # Fetch all facts including quarantined facts (to audit and clean up quarantined items safely)
        all_facts = self.fact_store.query(recallable_only=False)

        # 1. Enforce strict project grouping
        project_groups: Dict[str, List[Fact]] = {}
        for f in all_facts:
            proj = f.project or "default"
            if project and proj.lower() != project.lower():
                continue
            project_groups.setdefault(proj, []).append(f)

        new_suggestions: List[MaintenanceSuggestion] = []

        with self._lock:
            for proj, facts in project_groups.items():
                # Detect issues strictly within this project
                dupes = self._detect_duplicates(proj, facts)
                contradictions = self._detect_contradictions(proj, facts)
                outdated = self._detect_outdated(proj, facts)

                for sug in dupes + contradictions + outdated:
                    # Deduplicate suggestions by their target fingerprint
                    existing = self._find_existing_suggestion(sug)
                    if existing is not None:
                        # Keep existing status if already dismissed or approved
                        if existing.status != SuggestionStatus.PENDING:
                            continue
                        self._suggestions[existing.id] = sug
                        new_suggestions.append(sug)
                    else:
                        self._suggestions[sug.id] = sug
                        new_suggestions.append(sug)

            self._save_suggestions()

        return new_suggestions

    def _find_existing_suggestion(self, candidate: MaintenanceSuggestion) -> Optional[MaintenanceSuggestion]:
        """Find existing suggestion with same issue type and involved source facts."""
        c_set = set(candidate.source_fact_ids)
        for sug in self._suggestions.values():
            if sug.issue_type == candidate.issue_type and set(sug.source_fact_ids) == c_set:
                return sug
        return None

    # ------------------------------------------------------------------
    # Detection Sub-Routines (Strictly Within Project Scope)
    # ------------------------------------------------------------------

    def _detect_duplicates(self, project: str, facts: List[Fact]) -> List[MaintenanceSuggestion]:
        """Identify exact or high-lexical overlap duplicate memories."""
        suggestions: List[MaintenanceSuggestion] = []
        n = len(facts)
        seen_pairs: Set[Tuple[str, str]] = set()

        for i in range(n):
            f1 = facts[i]
            t1 = _normalize_tokens(f1.text)
            norm_text1 = re.sub(r"[^\w\s]", "", f1.text.lower()).strip()

            for j in range(i + 1, n):
                f2 = facts[j]
                pair_key = (min(f1.id, f2.id), max(f1.id, f2.id))
                if pair_key in seen_pairs:
                    continue

                t2 = _normalize_tokens(f2.text)
                norm_text2 = re.sub(r"[^\w\s]", "", f2.text.lower()).strip()

                is_exact = norm_text1 == norm_text2
                jaccard = _jaccard_similarity(t1, t2)
                is_high_overlap = jaccard >= 0.60 and len(t1) >= 3 and len(t2) >= 3

                # Substring containment check if length ratio is high
                is_sub = False
                if len(norm_text1) > 0 and len(norm_text2) > 0:
                    if norm_text1 in norm_text2 or norm_text2 in norm_text1:
                        shorter = min(len(norm_text1), len(norm_text2))
                        longer = max(len(norm_text1), len(norm_text2))
                        if shorter / longer >= 0.60:
                            is_sub = True

                if is_exact or is_high_overlap or is_sub:
                    seen_pairs.add(pair_key)

                    # Determine target fact to keep
                    # 1. Prefer verified over unverified
                    # 2. Prefer trusted over auto/untrusted
                    # 3. Prefer longer/more detailed text
                    # 4. Prefer newer fact
                    def _score_fact(f: Fact) -> Tuple[int, int, int, float]:
                        v_score = 1 if f.verified else 0
                        t_score = 2 if f.trust == TRUST_TRUSTED else (1 if f.trust == TRUST_AUTO else 0)
                        len_score = len(f.text)
                        return (v_score, t_score, len_score, f.created_at)

                    if _score_fact(f1) >= _score_fact(f2):
                        f_keep, f_remove = f1, f2
                    else:
                        f_keep, f_remove = f2, f1

                    quarantined = (f1.trust == TRUST_UNTRUSTED or f2.trust == TRUST_UNTRUSTED)

                    overlap_pct = int(jaccard * 100) if not is_exact else 100
                    reason = (
                        f"Found exact duplicate facts in project '{project}'."
                        if is_exact
                        else f"Found high lexical overlap ({overlap_pct}% token similarity) between facts in project '{project}'."
                    )

                    sug_id = f"sug_dup_{hashlib.sha256(f'{f1.id}:{f2.id}'.encode()).hexdigest()[:12]}"
                    suggestions.append(
                        MaintenanceSuggestion(
                            id=sug_id,
                            issue_type=MaintenanceIssueType.DUPLICATE,
                            project=project,
                            category=f_keep.category,
                            reason=reason,
                            source_fact_ids=[f1.id, f2.id],
                            source_facts=[f1.to_dict(), f2.to_dict()],
                            proposed_action=ProposedAction.MERGE,
                            proposed_resolution={
                                "target_fact_id": f_keep.id,
                                "merged_text": f_keep.text,
                                "facts_to_remove": [f_remove.id],
                                "quarantined_warning": quarantined,
                            },
                            quarantined_involved=quarantined,
                        )
                    )

        return suggestions

    def _detect_contradictions(self, project: str, facts: List[Fact]) -> List[MaintenanceSuggestion]:
        """Identify contradictory facts on the same topic/entity."""
        suggestions: List[MaintenanceSuggestion] = []
        n = len(facts)
        seen_pairs: Set[Tuple[str, str]] = set()

        for i in range(n):
            f1 = facts[i]
            t1 = _normalize_tokens(f1.text)

            for j in range(i + 1, n):
                f2 = facts[j]
                pair_key = (min(f1.id, f2.id), max(f1.id, f2.id))
                if pair_key in seen_pairs:
                    continue

                t2 = _normalize_tokens(f2.text)

                # Check 1: Direct Polar Negation on same subject
                # Subject tokens are tokens that are neither stop words nor polarity words
                subj1 = {w for w in t1 if w not in _STOP_WORDS and w not in _POSITIVE_INDICATORS and w not in _NEGATIVE_INDICATORS}
                subj2 = {w for w in t2 if w not in _STOP_WORDS and w not in _POSITIVE_INDICATORS and w not in _NEGATIVE_INDICATORS}

                subj_overlap = len(subj1 & subj2)
                has_subj_match = subj_overlap >= 2 or (len(subj1) > 0 and subj1 == subj2)

                has_pos1 = bool(t1 & _POSITIVE_INDICATORS)
                has_neg1 = bool(t1 & _NEGATIVE_INDICATORS)
                has_pos2 = bool(t2 & _POSITIVE_INDICATORS)
                has_neg2 = bool(t2 & _NEGATIVE_INDICATORS)

                polar_clash = (has_pos1 and has_neg2) or (has_neg1 and has_pos2)

                # Check 2: Conflicting config / entity assignment
                # E.g. "Database is PostgreSQL" vs "Database is SQLite"
                # "Port 8080" vs "Port 9090", "Theme dark" vs "Theme light"
                conflicting_assignment = False
                common_prefix_tokens = 0
                words1 = f1.text.lower().split()
                words2 = f2.text.lower().split()
                min_len = min(len(words1), len(words2))
                for w_idx in range(min_len):
                    if words1[w_idx] == words2[w_idx]:
                        common_prefix_tokens += 1
                    else:
                        break

                if common_prefix_tokens >= 2 and abs(len(words1) - len(words2)) <= 2:
                    # Differing tail words
                    tail1 = words1[common_prefix_tokens:]
                    tail2 = words2[common_prefix_tokens:]
                    if tail1 and tail2 and tail1 != tail2:
                        conflicting_assignment = True

                if (has_subj_match and polar_clash) or conflicting_assignment:
                    seen_pairs.add(pair_key)
                    quarantined = (f1.trust == TRUST_UNTRUSTED or f2.trust == TRUST_UNTRUSTED)

                    # Determine proposed resolution:
                    # If one is verified and the other unverified, supersede unverified with verified
                    # If one is newer, propose superseding the older entry
                    if f1.verified and not f2.verified:
                        f_keep, f_retire = f1, f2
                    elif f2.verified and not f1.verified:
                        f_keep, f_retire = f2, f1
                    elif f1.created_at >= f2.created_at:
                        f_keep, f_retire = f1, f2
                    else:
                        f_keep, f_retire = f2, f1

                    reason = (
                        f"Detected conflicting directives in project '{project}': "
                        f"'{f1.text}' vs '{f2.text}'."
                    )
                    sug_id = f"sug_contra_{hashlib.sha256(f'{f1.id}:{f2.id}'.encode()).hexdigest()[:12]}"
                    suggestions.append(
                        MaintenanceSuggestion(
                            id=sug_id,
                            issue_type=MaintenanceIssueType.CONTRADICTION,
                            project=project,
                            category=f1.category,
                            reason=reason,
                            source_fact_ids=[f1.id, f2.id],
                            source_facts=[f1.to_dict(), f2.to_dict()],
                            proposed_action=ProposedAction.SUPERSEDE,
                            proposed_resolution={
                                "keep_fact_id": f_keep.id,
                                "superseded_fact_id": f_retire.id,
                                "action_detail": f"Keep newer/verified fact ({f_keep.id}) and retire conflicting entry ({f_retire.id}).",
                                "quarantined_warning": quarantined,
                            },
                            quarantined_involved=quarantined,
                        )
                    )

        return suggestions

    def _detect_outdated(self, project: str, facts: List[Fact]) -> List[MaintenanceSuggestion]:
        """Identify outdated or stale memories superseded by newer facts or explicit markers."""
        suggestions: List[MaintenanceSuggestion] = []
        n = len(facts)
        seen_facts: Set[str] = set()

        # 1. Check explicit stale markers in metadata
        for f in facts:
            meta = f.metadata or {}
            is_explicit_stale = (
                meta.get("stale") is True
                or meta.get("deprecated") is True
                or str(meta.get("status", "")).lower() in ("outdated", "stale", "deprecated")
            )
            if is_explicit_stale and f.id not in seen_facts:
                seen_facts.add(f.id)
                quarantined = f.trust == TRUST_UNTRUSTED
                sug_id = f"sug_out_{hashlib.sha256(f.id.encode()).hexdigest()[:12]}"
                suggestions.append(
                    MaintenanceSuggestion(
                        id=sug_id,
                        issue_type=MaintenanceIssueType.OUTDATED,
                        project=project,
                        category=f.category,
                        reason=f"Memory is explicitly marked as {meta.get('status') or 'stale'} in its metadata.",
                        source_fact_ids=[f.id],
                        source_facts=[f.to_dict()],
                        proposed_action=ProposedAction.DELETE,
                        proposed_resolution={
                            "retire_fact_id": f.id,
                            "action_detail": f"Permanently retire outdated memory '{f.text[:60]}...'",
                            "quarantined_warning": quarantined,
                        },
                        quarantined_involved=quarantined,
                    )
                )

        # 2. Check for version upgrades / superseding facts
        # E.g. fact mentions "Node 18" and newer fact mentions "Node 20" or "Upgraded to Node 20"
        for i in range(n):
            f_older = facts[i]
            if f_older.id in seen_facts:
                continue

            v_match_older = re.search(r"\b(?:v|version)?\s*(\d+(?:\.\d+)*)\b", f_older.text.lower())
            if not v_match_older:
                continue

            for j in range(n):
                if i == j:
                    continue
                f_newer = facts[j]
                if f_newer.created_at <= f_older.created_at:
                    continue

                v_match_newer = re.search(r"\b(?:v|version)?\s*(\d+(?:\.\d+)*)\b", f_newer.text.lower())
                if not v_match_newer:
                    continue

                # Check if they share technology/entity tokens
                t_old = _normalize_tokens(f_older.text) - _STOP_WORDS
                t_new = _normalize_tokens(f_newer.text) - _STOP_WORDS
                overlap = t_old & t_new
                # Filter out raw version numbers from overlap
                common_entities = {w for w in overlap if not re.match(r"^\d+(\.\d+)*$", w)}

                if len(common_entities) >= 1:
                    is_upgrade_verb = any(
                        verb in f_newer.text.lower()
                        for verb in ("upgraded", "upgrade", "migrated", "migrate", "bumped", "switched", "updated")
                    )
                    ver_older = v_match_older.group(1)
                    ver_newer = v_match_newer.group(1)

                    if ver_older != ver_newer and (is_upgrade_verb or f_newer.created_at > f_older.created_at + 60):
                        seen_facts.add(f_older.id)
                        quarantined = (f_older.trust == TRUST_UNTRUSTED or f_newer.trust == TRUST_UNTRUSTED)
                        sug_id = f"sug_out_{hashlib.sha256(f'{f_older.id}:{f_newer.id}'.encode()).hexdigest()[:12]}"
                        suggestions.append(
                            MaintenanceSuggestion(
                                id=sug_id,
                                issue_type=MaintenanceIssueType.OUTDATED,
                                project=project,
                                category=f_older.category,
                                reason=(
                                    f"Fact '{f_older.text}' appears superseded by newer version/milestone "
                                    f"'{f_newer.text}' recorded later in project '{project}'."
                                ),
                                source_fact_ids=[f_older.id, f_newer.id],
                                source_facts=[f_older.to_dict(), f_newer.to_dict()],
                                proposed_action=ProposedAction.SUPERSEDE,
                                proposed_resolution={
                                    "keep_fact_id": f_newer.id,
                                    "superseded_fact_id": f_older.id,
                                    "action_detail": f"Keep newer fact ({f_newer.id}) and retire outdated entry ({f_older.id}).",
                                    "quarantined_warning": quarantined,
                                },
                                quarantined_involved=quarantined,
                            )
                        )
                        break

        return suggestions

    # ------------------------------------------------------------------
    # Suggestion Query & Inspection
    # ------------------------------------------------------------------

    def get_suggestions(
        self,
        project: Optional[str] = None,
        issue_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[MaintenanceSuggestion]:
        """Retrieve stored suggestions with optional filtering."""
        with self._lock:
            results = list(self._suggestions.values())

        if project:
            results = [s for s in results if s.project.lower() == project.lower()]
        if issue_type and issue_type != "all":
            results = [s for s in results if s.issue_type.lower() == issue_type.lower()]
        if status and status != "all":
            results = [s for s in results if s.status.lower() == status.lower()]

        # Sort pending first, then by created_at descending
        results.sort(key=lambda s: (0 if s.status == SuggestionStatus.PENDING else 1, -s.created_at))
        return results

    def get_suggestion(self, suggestion_id: str) -> Optional[MaintenanceSuggestion]:
        """Retrieve a specific suggestion by ID."""
        with self._lock:
            return self._suggestions.get(suggestion_id)

    # ------------------------------------------------------------------
    # Human Approval & Application
    # ------------------------------------------------------------------

    def approve_suggestion(
        self,
        suggestion_id: str,
        *,
        custom_text: Optional[str] = None,
        target_trust: Optional[str] = None,
        user_id: str = "admin",
        user_role: str = "admin",
    ) -> Dict[str, Any]:
        """Apply an approved maintenance suggestion with human authorization.

        CRITICAL SECURITY INVARIANTS:
        1. Quarantined memories can NEVER be promoted to trusted or auto status via consolidation.
        2. All written text is scrubbed of credentials and API keys.
        3. All written text is checked with InjectionScanner for prompt injection.
        4. No memory modification occurs without this explicit approval call.
        """
        with self._lock:
            sug = self._suggestions.get(suggestion_id)
            if sug is None:
                raise ValueError(f"Suggestion '{suggestion_id}' not found.")
            if sug.status != SuggestionStatus.PENDING:
                raise ValueError(f"Suggestion '{suggestion_id}' is already {sug.status}.")

            # Security Guard: Quarantine Protection
            if sug.quarantined_involved:
                if target_trust in (TRUST_TRUSTED, TRUST_AUTO):
                    raise PermissionError(
                        "Quarantined memories cannot be promoted to trusted status via memory consolidation."
                    )

            res = sug.proposed_resolution
            action = sug.proposed_action
            affected_facts: List[str] = []

            if action == ProposedAction.MERGE:
                target_id = res.get("target_fact_id")
                facts_to_remove = res.get("facts_to_remove", [])
                target_fact = self.fact_store.get(target_id)
                if not target_fact:
                    raise ValueError(f"Target fact '{target_id}' for merge no longer exists.")

                # Determine resulting trust tier
                # If ANY involved fact is quarantined, output MUST be quarantined
                if sug.quarantined_involved or target_fact.trust == TRUST_UNTRUSTED:
                    effective_trust = TRUST_UNTRUSTED
                elif target_trust:
                    effective_trust = target_trust
                else:
                    effective_trust = target_fact.trust

                # Scrub text
                final_text = custom_text or res.get("merged_text") or target_fact.text
                clean_text = scrub_sensitive_data(final_text).strip()

                # Prompt injection scan
                scanner = InjectionScanner()
                scan_res = scanner.scan(clean_text)
                if scan_res and not scan_res.is_clean:
                    effective_trust = TRUST_UNTRUSTED

                # Combine provenance metadata
                combined_meta = dict(target_fact.metadata or {})
                combined_meta["merged_at"] = time.time()
                combined_meta["merged_by"] = user_id
                combined_meta["consolidation_suggestion_id"] = sug.id
                existing_merged_from = list(combined_meta.get("merged_from_ids", []))
                for fid in sug.source_fact_ids:
                    if fid not in existing_merged_from and fid != target_id:
                        existing_merged_from.append(fid)
                combined_meta["merged_from_ids"] = existing_merged_from

                # Update target fact
                self.fact_store.update(
                    target_id,
                    text=clean_text,
                    trust=effective_trust,
                    metadata=scrub_metadata(combined_meta),
                )
                affected_facts.append(target_id)

                # Delete merged redundant facts
                for fid in facts_to_remove:
                    self.fact_store.delete(fid)
                    affected_facts.append(fid)

            elif action == ProposedAction.SUPERSEDE:
                keep_id = res.get("keep_fact_id")
                superseded_id = res.get("superseded_fact_id")
                if superseded_id:
                    self.fact_store.delete(superseded_id)
                    affected_facts.append(superseded_id)
                if keep_id:
                    # Update metadata on kept fact noting superseding
                    keep_fact = self.fact_store.get(keep_id)
                    if keep_fact:
                        meta = dict(keep_fact.metadata or {})
                        meta["superseded_facts"] = list(meta.get("superseded_facts", [])) + [superseded_id]
                        meta["maintenance_action"] = "supersede_approved"
                        self.fact_store.update(keep_id, metadata=meta)
                        affected_facts.append(keep_id)

            elif action == ProposedAction.DELETE:
                retire_id = res.get("retire_fact_id") or (sug.source_fact_ids[0] if sug.source_fact_ids else None)
                if retire_id:
                    self.fact_store.delete(retire_id)
                    affected_facts.append(retire_id)

            elif action == ProposedAction.MARK_FOR_REVIEW:
                for fid in sug.source_fact_ids:
                    fact = self.fact_store.get(fid)
                    if fact:
                        meta = dict(fact.metadata or {})
                        meta["needs_human_review"] = True
                        meta["maintenance_flag"] = sug.reason
                        self.fact_store.update(fid, metadata=meta)
                        affected_facts.append(fid)

            # Record resolution state
            sug.status = SuggestionStatus.APPROVED
            sug.resolved_at = time.time()
            sug.resolved_by = user_id
            self._save_suggestions()

        return {
            "status": "success",
            "suggestion_id": sug.id,
            "action_executed": action,
            "affected_facts": affected_facts,
            "resolved_at": sug.resolved_at,
            "resolved_by": sug.resolved_by,
        }

    # ------------------------------------------------------------------
    # Dismiss Suggestion
    # ------------------------------------------------------------------

    def dismiss_suggestion(
        self,
        suggestion_id: str,
        reason: Optional[str] = None,
        user_id: str = "admin",
    ) -> Dict[str, Any]:
        """Dismiss a suggestion without modifying any stored memory facts."""
        with self._lock:
            sug = self._suggestions.get(suggestion_id)
            if sug is None:
                raise ValueError(f"Suggestion '{suggestion_id}' not found.")
            if sug.status != SuggestionStatus.PENDING:
                raise ValueError(f"Suggestion '{suggestion_id}' is already {sug.status}.")

            sug.status = SuggestionStatus.DISMISSED
            sug.resolved_at = time.time()
            sug.resolved_by = user_id
            sug.dismiss_reason = reason or "Dismissed by operator."
            self._save_suggestions()

        return {
            "status": "success",
            "suggestion_id": sug.id,
            "resolved_at": sug.resolved_at,
            "resolved_by": sug.resolved_by,
            "dismiss_reason": sug.dismiss_reason,
        }
