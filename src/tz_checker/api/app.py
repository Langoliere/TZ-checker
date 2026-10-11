import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from tz_checker.config import get_settings
from tz_checker.llm.client import OllamaClient
from tz_checker.logging import configure_logging
from tz_checker.models.db import Document, FindingRecord, ReferenceChunk, ReferenceDocument
from tz_checker.models.schemas import DocumentResponse, FeedbackRequest, ReferenceMetadata
from tz_checker.parsers.docx_parser import parse_docx
from tz_checker.reports.generator import docx_report, markdown_report
from tz_checker.repositories.database import create_schema, get_session
from tz_checker.repositories.storage import LocalStorage
from tz_checker.retrieval.hybrid import hybrid_search
from tz_checker.services.tasks import process_document_task

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    create_schema()
    yield


app = FastAPI(title="TZ Checker", version="0.1.0", lifespan=lifespan)


# Идентификатор запроса возвращается клиенту и связывает события в структурных логах.
@app.middleware("http")
async def request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID", str(uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.get("/health")
def health(session: Session = Depends(get_session)):
    checks = {"database": False, "redis": False, "ollama": False}
    try:
        session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass
    try:
        from redis import Redis
        checks["redis"] = bool(Redis.from_url(settings.redis_url).ping())
    except Exception:
        pass
    try:
        checks["ollama"] = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2).is_success
    except Exception:
        pass
    return JSONResponse({"status": "ok" if checks["database"] else "degraded", "checks": checks}, status_code=200 if checks["database"] else 503)


@app.post("/v1/documents", response_model=DocumentResponse, status_code=202)
async def upload_document(file: UploadFile = File(...), session: Session = Depends(get_session)):
    if not file.filename or Path(file.filename).suffix.lower() != ".docx":
        raise HTTPException(415, "Only .docx files are supported")
    # Читаем на один байт больше лимита, чтобы обнаружить превышение без загрузки всего файла.
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if not content or len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File is empty or exceeds size limit")
    document = Document(filename=Path(file.filename).name, checksum=hashlib.sha256(content).hexdigest(), storage_key="")
    session.add(document)
    session.flush()
    document.storage_key = LocalStorage().save(document.id, document.filename, content)
    session.commit()
    # API отвечает сразу после постановки задачи и не ожидает parser или LLM.
    process_document_task.delay(str(document.id))
    return _response(document, session)


def _response(document: Document, session: Session) -> DocumentResponse:
    count = session.scalar(select(func.count()).select_from(FindingRecord).where(FindingRecord.document_id == document.id)) or 0
    return DocumentResponse(id=document.id, filename=document.filename, title=document.title, status=document.status, error=document.error, findings_count=count, created_at=document.created_at)


@app.get("/v1/documents", response_model=list[DocumentResponse])
def list_documents(session: Session = Depends(get_session)):
    return [_response(d, session) for d in session.scalars(select(Document).order_by(Document.created_at.desc()).limit(50))]


@app.get("/v1/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: UUID, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    return _response(document, session)


@app.post("/v1/documents/{document_id}/reprocess", status_code=202)
def reprocess(document_id: UUID, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    document.processing_version += 1
    document.status = "uploaded"
    document.error = None
    session.commit()
    process_document_task.delay(str(document.id))
    return {"document_id": document_id, "status": "uploaded"}


@app.get("/v1/documents/{document_id}/findings")
def get_findings(document_id: UUID, session: Session = Depends(get_session)):
    records = session.scalars(select(FindingRecord).where(FindingRecord.document_id == document_id)).all()
    return [{"id": str(record.id), "expert_status": record.expert_status, "expert_comment": record.expert_comment, **record.payload} for record in records]


@app.patch("/v1/findings/{finding_id}")
def feedback(finding_id: UUID, payload: FeedbackRequest, session: Session = Depends(get_session)):
    record = session.get(FindingRecord, finding_id)
    if not record:
        raise HTTPException(404, "Finding not found")
    record.expert_status, record.expert_comment = payload.status, payload.comment
    session.commit()
    return {"id": finding_id, "status": record.expert_status}


@app.get("/v1/documents/{document_id}/reports/{format}")
def report(document_id: UUID, format: str, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    findings = list(session.scalars(select(FindingRecord).where(FindingRecord.document_id == document_id)))
    if format == "markdown":
        return Response(markdown_report(document, findings), media_type="text/markdown", headers={"Content-Disposition": "attachment; filename=report.md"})
    if format == "docx":
        return Response(docx_report(document, findings), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": "attachment; filename=report.docx"})
    if format == "json":
        return [item.payload for item in findings]
    raise HTTPException(404, "Unknown report format")


@app.post("/v1/references", status_code=201)
async def upload_reference(file: UploadFile = File(...), metadata: str = Form("{}"), session: Session = Depends(get_session)):
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(415, "Only .docx files are supported")
    meta = ReferenceMetadata.model_validate_json(metadata)
    content = await file.read()
    reference = ReferenceDocument(filename=Path(file.filename).name, storage_key="", metadata_=meta.model_dump(), parsed_content={})
    session.add(reference); session.flush()
    reference.storage_key = LocalStorage().save(reference.id, reference.filename, content, "references")
    parsed = parse_docx(LocalStorage().path(reference.storage_key), str(reference.id))
    reference.parsed_content = parsed.model_dump(mode="json")
    # Единицей индексации служит раздел: это сохраняет смысл и точную ссылку на источник.
    texts = [f"{section.title}\n{section.text}" for section in parsed.sections]
    try:
        vectors = OllamaClient().embed(texts)
    except Exception as exc:
        raise HTTPException(503, "Embedding model is unavailable") from exc
    for section, chunk_text, vector in zip(parsed.sections, texts, vectors, strict=True):
        session.add(ReferenceChunk(reference_document_id=reference.id, section_id=section.section_id, location=section.paragraph_refs[0] if section.paragraph_refs else section.section_id, text=chunk_text, chunk_metadata=meta.model_dump(), embedding=vector))
    session.commit()
    return {"id": reference.id, "chunks": len(parsed.sections)}


@app.get("/v1/references/search")
def search_references(query: str, product_type: str | None = None, domain: str | None = None, status: str = "approved", limit: int = 5, session: Session = Depends(get_session)):
    chunks = list(session.scalars(select(ReferenceChunk)))
    # Метаданные фильтруются до ранжирования, чтобы устаревшие эталоны не влияли на выдачу.
    filtered = [chunk for chunk in chunks if chunk.chunk_metadata.get("status") == status and (not product_type or chunk.chunk_metadata.get("product_type") == product_type) and (not domain or chunk.chunk_metadata.get("domain") == domain)]
    try:
        query_vector = OllamaClient().embed([query])[0]
    except Exception as exc:
        raise HTTPException(503, "Embedding model is unavailable") from exc
    payload = [{"id": chunk.id, "document_id": chunk.reference_document_id, "section_id": chunk.section_id, "location": chunk.location, "text": chunk.text, "embedding": chunk.embedding, "metadata": chunk.chunk_metadata} for chunk in filtered]
    return [result.__dict__ for result in hybrid_search(query, query_vector, payload, min(limit, 20))]
