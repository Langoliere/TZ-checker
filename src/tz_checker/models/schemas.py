from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# Статусы отражают этапы конвейера и используются API для неблокирующего polling.
class ProcessingStatus(StrEnum):
    uploaded = "uploaded"
    parsing = "parsing"
    rule_check = "rule_check"
    retrieval = "retrieval"
    llm_review = "llm_review"
    report_generation = "report_generation"
    completed = "completed"
    failed = "failed"


class Severity(StrEnum):
    critical = "critical"
    major = "major"
    minor = "minor"
    advisory = "advisory"


class Paragraph(BaseModel):
    paragraph_id: str
    text: str
    style: str | None = None
    numbering: str | None = None


class Table(BaseModel):
    table_id: str
    caption: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class Section(BaseModel):
    section_id: str
    title: str
    level: int = 1
    text: str = ""
    paragraph_refs: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)


# Каноническое представление DOCX отделяет parser от правил, retrieval и отчетов.
class DocumentModel(BaseModel):
    document_id: str
    title: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    paragraphs: list[Paragraph] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)


class Reference(BaseModel):
    source: Literal["rag"] = "rag"
    document_id: str
    section_id: str | None = None
    quote: str


class Finding(BaseModel):
    finding_type: str
    severity: Severity
    status: Literal["violation", "potential_issue"]
    section_id: str | None = None
    location: str
    issue: str
    evidence: str
    reference: Reference | None = None
    recommendation: str
    source: Literal["rule", "rag", "llm"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    rule_id: str | None = None
    check_name: str | None = None

    # Вероятностные выводы нельзя публиковать без проверяемой привязки и обоснования.
    @model_validator(mode="after")
    def validate_probabilistic_finding(self) -> "Finding":
        if self.source in {"llm", "rag"}:
            if self.status != "potential_issue" or not self.location or not self.evidence:
                raise ValueError("LLM/RAG findings require potential_issue, location and evidence")
        if self.source == "rule" and self.status != "violation":
            raise ValueError("Rule findings must be violations")
        return self


class FindingsResponse(BaseModel):
    findings: list[Finding] = Field(default_factory=list, max_length=10)


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    title: str | None
    status: ProcessingStatus
    error: str | None
    findings_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackRequest(BaseModel):
    status: Literal["accepted", "rejected", "fixed"]
    comment: str | None = Field(default=None, max_length=2000)


class ReferenceMetadata(BaseModel):
    product_type: str | None = None
    domain: str | None = None
    customer: str | None = None
    status: Literal["approved", "deprecated"] = "approved"
    version: str = "1.0"
