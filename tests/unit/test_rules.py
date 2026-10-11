from pathlib import Path

from tz_checker.models.schemas import DocumentModel, Paragraph, Section
from tz_checker.rules.engine import RuleEngine

RULES = Path("src/tz_checker/rules/default_rules.yaml")

def test_required_section_and_forbidden_phrase():
    doc = DocumentModel(document_id="1", title="Тест", sections=[Section(section_id="1", title="Общие сведения", paragraph_refs=["p_1"])], paragraphs=[Paragraph(paragraph_id="p_1", text="Высокое качество в кратчайшие сроки")])
    findings = RuleEngine.from_yaml(RULES).run(doc)
    ids = {finding.rule_id for finding in findings}
    assert "TZ-STR-002" in ids
    assert "TZ-BAN-001" in ids
    assert all(f.status == "violation" for f in findings)
