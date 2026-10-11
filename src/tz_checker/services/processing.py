import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tz_checker.models.db import Document, FindingRecord
from tz_checker.models.schemas import DocumentModel, Finding
from tz_checker.parsers.docx_parser import parse_docx
from tz_checker.rules.engine import RuleEngine

RULES_PATH = Path(__file__).parents[1] / "rules" / "default_rules.yaml"


# Отпечаток обеспечивает детерминированную дедупликацию результатов разных проверок.
def fingerprint(finding: Finding) -> str:
    value = f"{finding.finding_type}|{finding.section_id}|{finding.location}|{finding.issue}".lower()
    return hashlib.sha256(value.encode()).hexdigest()


def deduplicate(findings: list[Finding]) -> list[Finding]:
    seen: set[str] = set()
    result = []
    for finding in findings:
        key = fingerprint(finding)
        if key not in seen:
            seen.add(key)
            result.append(finding)
    # Числовой порядок исключает зависимость сортировки от алфавита.
    order = {"critical": 0, "major": 1, "minor": 2, "advisory": 3}
    return sorted(result, key=lambda item: order[item.severity.value])


def process_document(session: Session, document_id: UUID, storage_path: Path) -> Document:
    document = session.scalar(select(Document).where(Document.id == document_id))
    if document is None:
        raise ValueError("Document not found")
    try:
        # Статус фиксируется после каждого этапа, чтобы UI видел прогресс и точку отказа.
        document.status = "parsing"
        document.error = None
        session.commit()
        parsed = parse_docx(storage_path, str(document.id))
        document.parsed_content = parsed.model_dump(mode="json")
        document.title = parsed.title
        document.status = "rule_check"
        session.commit()
        findings = deduplicate(RuleEngine.from_yaml(RULES_PATH).run(parsed))
        document.status = "report_generation"
        # Повторная обработка заменяет машинные результаты и не создает дубликаты.
        session.execute(delete(FindingRecord).where(FindingRecord.document_id == document.id))
        session.add_all([FindingRecord(document_id=document.id, fingerprint=fingerprint(f), payload=f.model_dump(mode="json")) for f in findings])
        document.status = "completed"
        session.commit()
        return document
    except Exception as exc:
        # Ошибка сохраняется в отдельной транзакции после отката незавершенного этапа.
        session.rollback()
        document.status = "failed"
        document.error = str(exc)[:2000]
        session.commit()
        raise


def parsed_document(document: Document) -> DocumentModel:
    if not document.parsed_content:
        raise ValueError("Document is not parsed")
    return DocumentModel.model_validate(document.parsed_content)


def findings_json(records: list[FindingRecord]) -> str:
    return json.dumps([record.payload for record in records], ensure_ascii=False, indent=2)
