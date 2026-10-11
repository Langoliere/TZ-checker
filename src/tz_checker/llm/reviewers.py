from typing import Any

from tz_checker.llm.client import OllamaClient
from tz_checker.models.schemas import FindingsResponse, Section

PROMPTS = {
    "structure_reviewer": "Сравни структуру ТЗ с эталонами. Найди только существенные потенциально недостающие разделы. Для location используй document или существующий section_id.",
    "section_completeness_reviewer": "Проверь полноту аспектов раздела относительно эталонов. Не копируй эталон механически.",
    "specificity_reviewer": "Найди неизмеримые, расплывчатые или непроверяемые требования. Цитируй точный paragraph id.",
    "consistency_reviewer": "Найди противоречия значений между предоставленными разделами и таблицами.",
    "mandatory_phrases_reviewer": "Проверь смысловое наличие обязательных формулировок из checklist.",
}


class Reviewers:
    def __init__(self, client: OllamaClient) -> None:
        self.client = client

    def review(self, check_name: str, section: Section | None, references: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> FindingsResponse:
        context = {"section": section.model_dump() if section else None, "references": references[:5], **(extra or {})}
        result = self.client.generate(PROMPTS[check_name], FindingsResponse, context, check_name)
        valid = [f for f in result.findings if f.location and f.evidence and f.status == "potential_issue"]
        for finding in valid:
            finding.check_name = check_name
            finding.source = "llm"
        return FindingsResponse(findings=valid[:5])
