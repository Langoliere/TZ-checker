import pytest
from pydantic import ValidationError

from tz_checker.models.schemas import Finding


def test_llm_finding_requires_evidence():
    with pytest.raises(ValidationError):
        Finding(finding_type="x", severity="major", status="potential_issue", location="p1", issue="x", evidence="", recommendation="x", source="llm", confidence=0.8)
