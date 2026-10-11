import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Документ хранит неизменяемую ссылку на оригинал и текущее состояние обработки.
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    title: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    parsed_content: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    processing_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    findings: Mapped[list["FindingRecord"]] = relationship(cascade="all, delete-orphan")


# Payload сохраняет единый Pydantic-контракт, а поля эксперта изменяются независимо.
class FindingRecord(Base):
    __tablename__ = "findings"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    expert_status: Mapped[str] = mapped_column(String(20), default="new")
    expert_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReferenceDocument(Base):
    __tablename__ = "reference_documents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    parsed_content: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Эталон индексируется фрагментами, чтобы retrieval возвращал секцию, а не весь документ.
class ReferenceChunk(Base):
    __tablename__ = "reference_chunks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reference_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reference_documents.id"), index=True)
    section_id: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)


# Журнал LLM-вызовов предназначен для аудита, отладки и последующей оценки качества.
class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    template_name: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(Text)
    context: Mapped[dict[str, Any]] = mapped_column(JSON)
    raw_response: Mapped[str | None] = mapped_column(Text)
    parsed_response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(default=False)
    validation_error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
