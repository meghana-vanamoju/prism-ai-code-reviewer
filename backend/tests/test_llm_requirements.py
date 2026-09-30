import json

import pytest

from app.models.job import SourceFile
from app.models.review import RequirementStatus
from app.services.llm_service import LLMService

service = LLMService()


class TestParseRequirementsReport:
    def _parse(self, payload):
        return service._parse_requirements_report(json.dumps(payload))

    def test_counts_coverage_and_normalises_fields(self):
        report = self._parse(
            {
                "summary": "mixed",
                "items": [
                    {
                        "id": "#12",
                        "title": "Login timeout",
                        "kind": "BUG",
                        "status": "IMPLEMENTED",
                        "evidence": ["src/auth.py:10"],
                        "gaps": "",
                        "notes": None,
                    },
                    {
                        "title": "Export",
                        "kind": "story",
                        "status": "missing",
                        "evidence": [],
                        "gaps": "no export code",
                    },
                ],
            }
        )
        assert report.summary == "mixed"
        assert report.implemented == 1
        assert report.missing == 1
        assert report.partial == 0
        assert report.coverage_pct == 50
        first, second = report.items
        assert first.id == "#12"
        assert first.kind == "bug"
        assert first.status == RequirementStatus.IMPLEMENTED
        assert second.id == "R2"  # positional fallback
        assert second.status == RequirementStatus.MISSING

    def test_unknown_status_falls_back_to_partial(self):
        report = self._parse(
            {"items": [{"id": "R1", "title": "t", "status": "unsure"}]}
        )
        assert report.items[0].status == RequirementStatus.PARTIAL
        assert report.partial == 1

    def test_unknown_kind_falls_back_to_other(self):
        report = self._parse(
            {"items": [{"id": "R1", "title": "t", "status": "implemented", "kind": "epic"}]}
        )
        assert report.items[0].kind == "other"

    def test_string_evidence_is_wrapped(self):
        report = self._parse(
            {
                "items": [
                    {
                        "id": "R1",
                        "title": "t",
                        "status": "implemented",
                        "evidence": "a.py:3",
                    }
                ]
            }
        )
        assert report.items[0].evidence == ["a.py:3"]

    def test_non_dict_items_are_ignored(self):
        report = self._parse({"items": ["nope", 5]})
        assert report.items == []
        assert report.coverage_pct == 0

    def test_non_list_items_yields_empty_report(self):
        report = self._parse({"items": "bad"})
        assert report.items == []

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            service._parse_requirements_report("{not json")


class TestBuildRequirementsPrompt:
    def test_includes_requirements_code_and_schema(self):
        files = [SourceFile(path="a.py", content="x = 1", language="python", size=5)]
        prompt = service._build_requirements_prompt(
            requirements="R1 do the thing", files=files, memories=[]
        )
        assert "REQUIREMENTS TO CHECK" in prompt
        assert "R1 do the thing" in prompt
        assert "--- FILE: a.py (python) ---" in prompt
        assert "implemented|partial|missing" in prompt

    def test_truncates_long_requirements(self):
        prompt = service._build_requirements_prompt(
            requirements="R" * 10_000, files=[], memories=[]
        )
        assert "[truncated]" in prompt

    def test_omits_files_over_budget(self):
        files = [
            SourceFile(path="big.py", content="y = 2\n" * 5_000, language="python", size=40_000),
            SourceFile(path="small.py", content="z = 3", language="python", size=6),
        ]
        prompt = service._build_requirements_prompt(
            requirements="R1", files=files, memories=[]
        )
        assert "Omitted 1 file(s)" in prompt
        assert "small.py" in prompt
