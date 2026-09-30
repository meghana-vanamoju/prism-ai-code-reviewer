import json
from types import SimpleNamespace

from app.models.review import MemoryUsed
from app.services.llm_service import LLMService

service = LLMService()

MEMORY = MemoryUsed(id="mem-1", text="Use Decimal for monetary values", type="observation")


class TestParseFileReview:
    def _parse(self, payload, path="src/billing.py"):
        return service._parse_file_review(json.dumps(payload), path=path)

    def test_sets_file_and_coerces_line_numbers(self):
        review = self._parse(
            {
                "summary": "s",
                "issues": [
                    {
                        "severity": "high",
                        "title": "t",
                        "description": "d",
                        "recommendation": "r",
                        "line": "42",
                        "end_line": 45,
                    }
                ],
                "suggestions": ["one"],
            }
        )
        issue = review.issues[0]
        assert issue.file == "src/billing.py"
        assert issue.line == 42
        assert issue.end_line == 45
        assert review.suggestions == ["one"]

    def test_invalid_line_becomes_none(self):
        review = self._parse(
            {
                "summary": "s",
                "issues": [
                    {
                        "severity": "low",
                        "title": "t",
                        "description": "",
                        "recommendation": "",
                        "line": "not-a-number",
                        "end_line": 0,
                    }
                ],
            }
        )
        issue = review.issues[0]
        assert issue.line is None
        assert issue.end_line is None

    def test_end_line_before_line_is_clamped(self):
        review = self._parse(
            {
                "summary": "s",
                "issues": [
                    {
                        "severity": "medium",
                        "title": "t",
                        "description": "",
                        "recommendation": "",
                        "line": 10,
                        "end_line": 4,
                    }
                ],
            }
        )
        assert review.issues[0].end_line == 10

    def test_unknown_severity_falls_back_to_suggestion(self):
        review = self._parse(
            {
                "summary": "s",
                "issues": [
                    {
                        "severity": "blocker",
                        "title": "t",
                        "description": "",
                        "recommendation": "",
                    }
                ],
            }
        )
        assert review.issues[0].severity.value == "suggestion"

    def test_empty_memory_reference_becomes_none(self):
        review = self._parse(
            {
                "summary": "s",
                "issues": [
                    {
                        "severity": "low",
                        "title": "t",
                        "description": "",
                        "recommendation": "",
                        "memory_reference": "  ",
                    }
                ],
            }
        )
        assert review.issues[0].memory_reference is None

    def test_non_dict_issues_are_dropped(self):
        review = self._parse({"summary": "s", "issues": ["bad", 42]})
        assert review.issues == []


class TestFilePrompt:
    def test_full_file_prompt_numbers_lines(self):
        prompt = service._build_file_prompt(
            path="app.py",
            content="x = 1\ny = 2\n",
            language="python",
            memories=[MEMORY],
            focus="security",
            is_diff=False,
        )
        assert "FILE: app.py (python)" in prompt
        assert "| x = 1" in prompt
        assert "| y = 2" in prompt
        assert "[1] Use Decimal for monetary values" in prompt
        assert "SPECIFIC REVIEW FOCUS: security" in prompt
        assert '"line": 12' in prompt

    def test_diff_prompt_uses_diff_block(self):
        prompt = service._build_file_prompt(
            path="app.py",
            content="@@ -1,2 +1,2 @@\n-a\n+b\n",
            language="python",
            memories=[],
            focus=None,
            is_diff=True,
        )
        assert "UNIFIED DIFF FOR: app.py" in prompt
        assert "```diff" in prompt
        assert "NEW file numbering" in prompt
        assert "FILE: app.py" not in prompt


import asyncio

import pytest

from app.services import llm_service as llm_module


class FakeHTTPError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status_code = status


def _response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _service(outcomes):
    completions = FakeCompletions(outcomes)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    svc = llm_module.LLMService()
    svc._client = client
    return svc, completions


def _install_clock(monkeypatch):
    """Replace sleep + monotonic so backoff/slot waits are instant but ordered."""
    state = {"t": 1000.0, "delays": []}

    def now():
        return state["t"]

    async def fake_sleep(seconds):
        state["delays"].append(seconds)
        state["t"] += float(seconds)

    monkeypatch.setattr(llm_module.time, "monotonic", now)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return state


GOOD_JSON = json.dumps({"summary": "ok", "issues": [], "suggestions": []})


@pytest.mark.asyncio
async def test_file_review_retries_rate_limit_then_succeeds(monkeypatch):
    clock = _install_clock(monkeypatch)
    svc, completions = _service(
        [
            FakeHTTPError(429, "Rate limit reached ... Please try again in 8.5s"),
            _response(GOOD_JSON),
        ]
    )

    review = await svc.generate_file_review(
        path="app.py", content="x = 1", language="python", memories=[]
    )

    assert review.summary == "ok"
    assert completions.calls == 2
    assert clock["delays"] and 8.5 <= clock["delays"][0] < 12


@pytest.mark.asyncio
async def test_file_review_gives_up_after_max_attempts(monkeypatch):
    _install_clock(monkeypatch)
    svc, completions = _service(
        [FakeHTTPError(429, "rate_limit_exceeded")] * llm_module.MAX_LLM_ATTEMPTS
    )

    with pytest.raises(RuntimeError, match="rate_limit_exceeded"):
        await svc.generate_file_review(
            path="app.py", content="x = 1", language="python", memories=[]
        )
    assert completions.calls == llm_module.MAX_LLM_ATTEMPTS


@pytest.mark.asyncio
async def test_file_review_does_not_retry_non_retryable_errors(monkeypatch):
    async def fake_sleep(seconds):
        pytest.fail("should not sleep for non-retryable errors")

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    svc, completions = _service([FakeHTTPError(401, "invalid api key")])

    with pytest.raises(RuntimeError, match="invalid api key"):
        await svc.generate_file_review(
            path="app.py", content="x = 1", language="python", memories=[]
        )
    assert completions.calls == 1


@pytest.mark.asyncio
async def test_file_review_retries_empty_json_generation(monkeypatch):
    _install_clock(monkeypatch)
    svc, completions = _service(
        [
            FakeHTTPError(
                400,
                "Failed to validate JSON ... 'code': 'json_validate_failed'",
            ),
            _response(GOOD_JSON),
        ]
    )

    review = await svc.generate_file_review(
        path="app.py", content="x = 1", language="python", memories=[]
    )
    assert review.summary == "ok"
    assert completions.calls == 2


@pytest.mark.asyncio
async def test_successful_call_paces_followup_to_tpm_budget(monkeypatch):
    clock = _install_clock(monkeypatch)
    svc, completions = _service([_response(GOOD_JSON)])

    await svc.generate_file_review(
        path="app.py", content="x = 1", language="python", memories=[]
    )

    # The next call must wait for this one's share of the TPM budget.
    assert svc._next_slot > clock["t"]


@pytest.mark.asyncio
async def test_serialized_calls_wait_for_paced_slots(monkeypatch):
    clock = _install_clock(monkeypatch)
    svc, completions = _service([_response(GOOD_JSON), _response(GOOD_JSON)])

    await svc.generate_file_review(
        path="a.py", content="x = 1", language="python", memories=[]
    )
    before = clock["t"]
    await svc.generate_file_review(
        path="b.py", content="y = 2", language="python", memories=[]
    )

    assert completions.calls == 2
    assert clock["t"] > before
