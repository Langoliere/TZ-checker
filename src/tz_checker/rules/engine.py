import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from tz_checker.models.schemas import DocumentModel, Finding, Severity


class Rule(BaseModel):
    rule_id: str
    name: str
    severity: Severity
    scope: str
    status: str = "violation"
    condition: dict[str, Any]
    message: str
    recommendation: str


class RuleEngine:
    def __init__(self, rules: list[Rule]) -> None:
        self.rules = rules

    # Валидация Pydantic не позволяет некорректному правилу попасть в выполнение.
    @classmethod
    def from_yaml(cls, path: Path) -> "RuleEngine":
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls([Rule.model_validate(item) for item in payload.get("rules", [])])

    def run(self, document: DocumentModel) -> list[Finding]:
        findings: list[Finding] = []
        for rule in self.rules:
            violations = self._evaluate(rule, document)
            for location, section_id, evidence in violations:
                findings.append(Finding(
                    finding_type=rule.name, severity=rule.severity, status="violation",
                    section_id=section_id, location=location, issue=rule.message,
                    evidence=evidence, recommendation=rule.recommendation,
                    source="rule", confidence=1.0, rule_id=rule.rule_id,
                ))
        return findings

    def _evaluate(self, rule: Rule, doc: DocumentModel) -> list[tuple[str, str | None, str]]:
        condition = rule.condition
        all_text = "\n".join(p.text for p in doc.paragraphs)
        section_titles = [s.title.lower() for s in doc.sections]
        result: list[tuple[str, str | None, str]] = []
        for required in condition.get("required_sections", []):
            if not any(required.lower() in title for title in section_titles):
                result.append(("document", None, f"Раздел «{required}» не найден"))
        for phrase in condition.get("required_phrases", []):
            if phrase.lower() not in all_text.lower():
                result.append(("document", None, f"Формулировка «{phrase}» не найдена"))
        for phrase in condition.get("forbidden_phrases", []):
            for paragraph in doc.paragraphs:
                if phrase.lower() in paragraph.text.lower():
                    result.append((paragraph.paragraph_id, self._section_for(doc, paragraph.paragraph_id), paragraph.text))
        # Таблица выбирается по подписи, после чего проверяются схема и заполненность.
        table_columns = condition.get("required_table_columns")
        if table_columns:
            matching = [t for t in doc.tables if condition.get("table_caption", "").lower() in t.caption.lower()]
            if not matching:
                result.append(("document", None, "Требуемая таблица не найдена"))
            for table in matching:
                missing = [c for c in table_columns if not any(c.lower() in x.lower() for x in table.columns)]
                if missing:
                    result.append((table.table_id, self._table_section(doc, table.table_id), f"Нет колонок: {', '.join(missing)}"))
                if condition.get("require_non_empty") and (not table.rows or any(not cell for row in table.rows for cell in row)):
                    result.append((table.table_id, self._table_section(doc, table.table_id), "Таблица содержит пустые ячейки"))
        pattern = condition.get("required_reference_pattern")
        if pattern and not re.search(pattern, all_text, re.IGNORECASE):
            result.append(("document", None, f"Не найдена нормативная ссылка по шаблону {pattern}"))
        # Значения одного параметра нормализуются, чтобы обнаружить расхождения между разделами.
        parameter = condition.get("consistent_parameter")
        if parameter:
            values: dict[str, list[str]] = {}
            regex = re.compile(rf"{re.escape(parameter)}\D{{0,30}}(\d+(?:[.,]\d+)?)", re.IGNORECASE)
            for p in doc.paragraphs:
                match = regex.search(p.text)
                if match:
                    values.setdefault(match.group(1).replace(",", "."), []).append(p.paragraph_id)
            if len(values) > 1:
                refs = [ref for group in values.values() for ref in group]
                result.append((refs[0], self._section_for(doc, refs[0]), f"Обнаружены разные значения: {', '.join(values)}"))
        return result

    @staticmethod
    def _section_for(doc: DocumentModel, paragraph_id: str) -> str | None:
        return next((s.section_id for s in doc.sections if paragraph_id in s.paragraph_refs), None)

    @staticmethod
    def _table_section(doc: DocumentModel, table_id: str) -> str | None:
        return next((s.section_id for s in doc.sections if table_id in s.tables), None)
