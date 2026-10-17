"""Ultron Autonomous Desktop & System Agent Subsystem.

Provides lightweight local System Catalog RAG, Desktop Agent Orchestration,
native Windows application and Chrome profile launching, Explorer navigation,
and ironclad safety guardrails.
"""

from openjarvis.desktop.catalog_rag import SystemCatalogRAG, SystemItem
from openjarvis.desktop.orchestrator import (
    DesktopOrchestrator,
    DesktopDirectiveResult,
    get_desktop_orchestrator,
)

__all__ = [
    "SystemCatalogRAG",
    "SystemItem",
    "DesktopOrchestrator",
    "DesktopDirectiveResult",
    "get_desktop_orchestrator",
]
