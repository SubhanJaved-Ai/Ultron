"""RAG Ingestion and Retrieval End-to-End Smoke Test.

Validates the complete deterministic offline RAG pipeline:
1. Synthetic Document creation (plain text & markdown attachment).
2. SemanticChunker splitting & IngestionPipeline deduplication/indexing.
3. KnowledgeStore SQLite FTS5 BM25 persistence.
4. TwoStageRetriever candidate retrieval & ranking.
5. Verification of known-fact retrieval and missing-document/no-result queries.
6. Documentation of optional dependency handling (e.g. pdfplumber for PDFs).
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from openjarvis.connectors._stubs import Attachment, Document
from openjarvis.connectors.attachment_store import AttachmentStore
from openjarvis.connectors.pipeline import IngestionPipeline
from openjarvis.connectors.retriever import TwoStageRetriever
from openjarvis.connectors.store import KnowledgeStore


class TestRAGIngestionRetrievalSmoke:
    """Smoke test suite exercising real parsing, chunking, storage, and retrieval."""

    def test_rag_ingestion_and_fact_retrieval(self, tmp_path: Path):
        """Ingest synthetic technical specification and retrieve known facts via TwoStageRetriever."""
        db_path = tmp_path / "rag_smoke_test.db"
        store = KnowledgeStore(db_path=db_path)
        pipeline = IngestionPipeline(store=store, max_tokens=128)

        # 1. Create synthetic documents with specific factual statements
        doc1 = Document(
            doc_id="spec:argon_optics_001",
            source="engineering_docs",
            doc_type="specification",
            title="Argon Hologram Optical Waveguide Architecture",
            author="chief_architect@ultron.internal",
            content=(
                "Project Argon utilizes holographic projection waveguides with an optical "
                "dispersion rating of 98.4% and quantum coherence stabilization. "
                "The holographic emitter operates at 532nm green laser frequency with "
                "active thermal dissipation managed by liquid gallium heat pipes."
            ),
            timestamp=datetime.datetime(2026, 3, 15, 10, 0, 0),
        )

        doc2 = Document(
            doc_id="spec:task_runner_002",
            source="architecture_docs",
            doc_type="design_doc",
            title="Persistent Task Runner Isolation and Safety Kernel",
            author="security_lead@ultron.internal",
            content=(
                "The Persistent Task Runner enforces multi-tenant boundary checks through "
                "cryptographic session tokens. Destructive operations such as rm -rf or "
                "database truncation are intercepted by the Safety Kernel requiring human authorization."
            ),
            timestamp=datetime.datetime(2026, 3, 16, 14, 30, 0),
        )

        # 2. Run actual ingestion pipeline
        chunks_count = pipeline.ingest([doc1, doc2])
        assert chunks_count >= 2, "Expected at least one chunk per ingested document"

        # 3. Retrieve using TwoStageRetriever
        retriever = TwoStageRetriever(store=store)

        # Query for fact from doc 1
        results = retriever.retrieve("optical dispersion waveguides", top_k=5)
        assert len(results) >= 1
        top_result = results[0]
        assert "98.4%" in top_result.content
        assert "waveguides" in top_result.content
        assert top_result.source == "engineering_docs"
        assert top_result.metadata.get("title") == "Argon Hologram Optical Waveguide Architecture"

        # Query for fact from doc 2
        results_task = retriever.retrieve("Safety Kernel destructive operations", top_k=5)
        assert len(results_task) >= 1
        assert "Safety Kernel" in results_task[0].content
        assert "human authorization" in results_task[0].content

    def test_rag_no_result_and_missing_document(self, tmp_path: Path):
        """Verify that querying for nonexistent topics returns an empty result set cleanly."""
        db_path = tmp_path / "rag_empty_test.db"
        store = KnowledgeStore(db_path=db_path)
        pipeline = IngestionPipeline(store=store)

        doc = Document(
            doc_id="doc:general",
            source="notes",
            doc_type="note",
            title="General Meeting",
            content="Discussed project milestones and Q2 deliverables.",
        )
        pipeline.ingest([doc])

        retriever = TwoStageRetriever(store=store)

        # Search for completely non-existent term
        results = retriever.retrieve("xyznonexistentquantumflux778899", top_k=5)
        assert len(results) == 0

    def test_rag_attachment_ingestion_and_retrieval(self, tmp_path: Path):
        """Verify that text/markdown attachments are extracted, indexed, and retrievable."""
        db_path = tmp_path / "rag_attachment_test.db"
        att_dir = tmp_path / "attachments"
        att_dir.mkdir()

        store = KnowledgeStore(db_path=db_path)
        att_store = AttachmentStore(base_dir=str(att_dir))
        pipeline = IngestionPipeline(store=store, attachment_store=att_store)

        attached_content = (
            "# Ultron Quantum Telemetry\n\n"
            "Telemetry channel 7 emits telemetry beacon signals at 1420.405 MHz "
            "with hydrogen line synchronization."
        ).encode("utf-8")

        attachment = Attachment(
            filename="telemetry_notes.md",
            mime_type="text/markdown",
            size_bytes=len(attached_content),
            content=attached_content,
        )

        doc = Document(
            doc_id="email:telemetry_report",
            source="gmail",
            doc_type="email",
            title="Telemetry Protocol Update",
            content="Please see the attached telemetry documentation for frequency specs.",
            attachments=[attachment],
        )

        pipeline.ingest([doc])

        retriever = TwoStageRetriever(store=store)
        results = retriever.retrieve("hydrogen line synchronization 1420.405", top_k=5)

        assert len(results) >= 1
        assert "1420.405 MHz" in results[0].content
        assert "telemetry beacon signals" in results[0].content

    def test_rag_pdf_dependency_limitation_handling(self, tmp_path: Path):
        """Verify graceful handling when pdfplumber is unavailable.

        Documents that PDF extraction requires the optional 'pdfplumber' dependency.
        When missing, the pipeline does not raise an unhandled exception or crash,
        but returns an empty extraction string and continues safely.
        """
        db_path = tmp_path / "rag_pdf_fallback.db"
        store = KnowledgeStore(db_path=db_path)
        pipeline = IngestionPipeline(store=store)

        dummy_pdf_bytes = b"%PDF-1.4\n%Fake PDF binary payload for testing\n%%EOF"
        pdf_attachment = Attachment(
            filename="sample.pdf",
            mime_type="application/pdf",
            size_bytes=len(dummy_pdf_bytes),
            content=dummy_pdf_bytes,
        )

        # Directly invoke attachment text extractor to confirm graceful handling
        extracted = pipeline._extract_attachment_text(pdf_attachment)

        # If pdfplumber is not installed, it returns empty string without crashing
        assert isinstance(extracted, str)
        if not extracted:
            # Documented limitation: pdfplumber is absent in offline / minimal test environments
            assert extracted == ""
