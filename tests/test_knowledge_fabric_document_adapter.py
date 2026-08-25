from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from echo_masque.knowledge_fabric_document_adapter import (
    DocumentRequiresOcr,
    KnowledgeFabricDocumentAdapter,
    SourceDocumentAdapterError,
    SourceDocumentInput,
)
from echo_masque.knowledge_fabric_document_policy import (
    document_filename_is_safe,
    document_format,
    document_requires_ocr,
)
from echo_masque.knowledge_object_storage import StoredKnowledgeObject
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str, dict[str, str]]] = {}
        self.put_calls = 0

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> StoredKnowledgeObject:
        self.put_calls += 1
        self.objects.setdefault(object_key, (content, content_type, dict(metadata)))
        return StoredKnowledgeObject(
            provider="cloudflare_r2",
            bucket="knowledge-private",
            object_key=object_key,
            content_sha256=sha256(content).hexdigest(),
            byte_size=len(content),
            content_type=content_type,
        )

    def get_private(self, *, object_key: str) -> bytes:
        return self.objects[object_key][0]

    def delete_private(self, *, object_key: str) -> bool:
        return self.objects.pop(object_key, None) is not None


def _input(*, filename: str, content: bytes, content_type: str) -> SourceDocumentInput:
    return SourceDocumentInput(
        source_id="source-document",
        version_key="revision-1",
        idempotency_key="document-delivery-1",
        canonical_locator="https://docs.example.test/imported/source",
        filename=filename,
        content=content,
        content_type=content_type,
        title="Imported source",
        published_at=datetime(2026, 8, 25, tzinfo=UTC),
    )


def _service(
    tmp_path: Path,
) -> tuple[
    FakeObjectStorage,
    KnowledgeFabricContentRepository,
    KnowledgeFabricDocumentAdapter,
    str,
]:
    database = Database(f"sqlite:///{tmp_path / 'document-adapter.db'}")
    database.initialize()
    storage = FakeObjectStorage()
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Document Fabric",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type="uploaded_document",
        locator="https://docs.example.test/imported/source",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    return (
        storage,
        KnowledgeFabricContentRepository(database, object_storage=storage),
        KnowledgeFabricDocumentAdapter(),
        source.id,
    )


def test_markdown_fixture_preserves_sections_blocks_links_lists_tables_and_lines() -> None:
    content = (
        Path(__file__).parent / "fixtures" / "knowledge_fabric" / "structured.md"
    ).read_bytes()

    snapshot = KnowledgeFabricDocumentAdapter().build_snapshot(
        _input(filename="structured.md", content=content, content_type="text/markdown")
    )

    document = snapshot.documents[0]
    assert [
        (item.structural_path, item.parent_path, item.heading) for item in document.sections
    ] == [
        ("heading:0", None, "Overview"),
        ("heading:1", "heading:0", "Details"),
    ]
    blocks = {item.block_type: item for item in document.blocks}
    linked_paragraph = next(item for item in document.blocks if item.coordinates.get("links"))
    assert linked_paragraph.coordinates["links"] == ["https://docs.example.test/handbook"]
    assert blocks["list"].text_content == "- first item\n- second item"
    assert blocks["table"].coordinates["line_start"] == 8
    assert document.blocks[-1].coordinates["line_start"] == 14
    assert snapshot.artifact_content == content
    assert snapshot.metadata == {
        "adapter": "document",
        "filename": "structured.md",
        "format": "markdown",
    }


def test_docx_fixture_preserves_heading_list_table_link_and_image_relationships() -> None:
    snapshot = KnowledgeFabricDocumentAdapter().build_snapshot(
        _input(
            filename="structured.docx",
            content=_docx_fixture(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    )

    document = snapshot.documents[0]
    assert [(item.heading, item.coordinates) for item in document.sections] == [
        ("Overview", {"paragraph": 0, "level": 1}),
    ]
    blocks = {item.block_type: item for item in document.blocks}
    assert blocks["list_item"].text_content == "First item"
    assert blocks["paragraph"].coordinates["links"] == ["https://docs.example.test/reference"]
    assert blocks["image_reference"].coordinates["image_relationships"] == ["media/image1.png"]
    assert blocks["table"].text_content == "name\tvalue\nalpha\tbeta"
    assert blocks["table"].coordinates == {"table": 0, "row_count": 2}


def test_pdf_digital_and_scanned_branches_are_explicit() -> None:
    adapter = KnowledgeFabricDocumentAdapter()
    digital = adapter.build_snapshot(
        _input(filename="digital.pdf", content=_digital_pdf(), content_type="application/pdf")
    )

    block = digital.documents[0].blocks[0]
    assert block.text_content == "Digital PDF evidence"
    assert block.coordinates == {"page": 1, "text_layer": True}

    with pytest.raises(DocumentRequiresOcr):
        adapter.build_snapshot(
            _input(filename="scanned.pdf", content=_blank_pdf(), content_type="application/pdf")
        )


def test_manual_text_snapshot_publishes_one_private_raw_artifact_and_source_evidence(
    tmp_path: Path,
) -> None:
    storage, content, adapter, source_id = _service(tmp_path)
    snapshot = adapter.manual_text(
        source_id=source_id,
        version_key="manual-revision-1",
        idempotency_key="manual-delivery-1",
        canonical_locator="https://docs.example.test/imported/manual",
        title="Manual note",
        text="First paragraph.\n\nSecond paragraph.",
        published_at=datetime(2026, 8, 25, tzinfo=UTC),
    )
    from echo_masque.knowledge_fabric_ingestion import KnowledgeFabricIngestionService

    service = KnowledgeFabricIngestionService(
        content, storage, object_key_prefix="knowledge-fabric"
    )
    version = service.ingest_snapshot(snapshot)
    again = service.ingest_snapshot(snapshot)

    assert again.id == version.id
    assert storage.put_calls == 1
    artifact = content.get_artifact(version.artifact_id)
    assert artifact is not None
    assert storage.get_private(object_key=artifact.object_key) == snapshot.artifact_content
    evidence = content.list_evidence_units(version.id)
    assert [(item.evidence_locator, item.coordinates_json) for item in evidence] == [
        ("https://docs.example.test/imported/manual#paragraph:0", '{"line_end":1,"line_start":1}'),
        ("https://docs.example.test/imported/manual#paragraph:1", '{"line_end":3,"line_start":3}'),
    ]


def test_document_policy_rejects_paths_and_distinguishes_supported_and_scanned_content() -> None:
    assert document_filename_is_safe("note.md")
    assert not document_filename_is_safe("   ")
    assert not document_filename_is_safe("../note.md")
    assert not document_filename_is_safe("folder/note.md")
    assert not document_filename_is_safe("folder\\note.md")
    assert (
        document_format(
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="source.bin",
        )
        == "docx"
    )
    assert document_format(content_type="application/octet-stream", filename="note.docx") == "docx"
    assert (
        document_format(
            content_type="application/pdf; charset=binary; version=1",
            filename="source.bin",
        )
        == "pdf"
    )
    assert document_format(content_type="application/octet-stream", filename="source.pdf") == "pdf"
    assert document_format(content_type="text/markdown", filename="source.bin") == "markdown"
    assert document_format(content_type="text/x-markdown", filename="source.bin") == "markdown"
    assert (
        document_format(content_type="application/octet-stream", filename="source.markdown")
        == "markdown"
    )
    assert (
        document_format(content_type="text/plain; charset=utf-8", filename="source.bin") == "text"
    )
    assert document_format(content_type="text/csv", filename="source.bin") == "text"
    assert document_format(content_type="application/octet-stream", filename="source.log") == "text"
    assert document_format(content_type="application/octet-stream", filename="archive.bin") is None
    assert document_requires_ocr(("", "  "))
    assert not document_requires_ocr(("", "Digital layer"))

    with pytest.raises(SourceDocumentAdapterError):
        KnowledgeFabricDocumentAdapter().build_snapshot(
            _input(
                filename="../not-a-document.md", content=b"# invalid", content_type="text/markdown"
            )
        )


def _docx_fixture() -> bytes:
    document = b"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
 <w:body>
  <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Overview</w:t></w:r></w:p>
  <w:p><w:pPr><w:numPr/></w:pPr><w:r><w:t>First item</w:t></w:r></w:p>
  <w:p><w:hyperlink r:id="rIdLink"><w:r><w:t>Reference</w:t></w:r></w:hyperlink></w:p>
  <w:p><w:r><w:drawing><a:blip r:embed="rIdImage"/></w:drawing></w:r></w:p>
  <w:tbl>
   <w:tr><w:tc><w:p><w:r><w:t>name</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>value</w:t></w:r></w:p></w:tc></w:tr>
   <w:tr><w:tc><w:p><w:r><w:t>alpha</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>beta</w:t></w:r></w:p></w:tc></w:tr>
  </w:tbl>
 </w:body>
</w:document>"""
    relationships = (
        b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rIdLink" Target="https://docs.example.test/reference" """
        b"""TargetMode="External" Type="hyperlink"/>
 <Relationship Id="rIdImage" Target="media/image1.png" Type="image"/>
</Relationships>"""
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", relationships)
    return stream.getvalue()


def _digital_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )
    contents = DecodedStreamObject()
    contents.set_data(b"BT /F1 12 Tf 72 720 Td (Digital PDF evidence) Tj ET")
    page[NameObject("/Contents")] = contents
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()
