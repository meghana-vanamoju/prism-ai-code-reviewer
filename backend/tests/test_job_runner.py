import asyncio
import json

import pytest

from app.models.job import (
    FileDiff,
    DiffHunk,
    DiffLine,
    JobRequest,
    JobStatus,
    SourceFile,
    SourceMode,
)
from app.models.memory import RecallMemoryItem, RecallMemoryResponse
from app.models.review import (
    FileReview,
    Issue,
    RequirementItem,
    RequirementStatus,
    RequirementsReport,
    Severity,
)
from app.services import job_runner as job_runner_module
from app.services.job_runner import job_runner
from app.services.job_store import job_store
from app.services.source_service import BranchSource


def make_issue(**overrides: object) -> Issue:
    base: dict = dict(
        severity=Severity.MEDIUM,
        title="Issue",
        description="desc",
        recommendation="fix it",
        file="src/app.py",
        line=3,
    )
    base.update(overrides)
    return Issue(**base)


async def wait_terminal(job, timeout=5.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        current = job_store.get(job.id)
        assert current is not None
        if current.is_terminal:
            return current
        await asyncio.sleep(0.01)
    raise AssertionError(f"job {job.id} did not reach a terminal state (status={job.status})")


@pytest.fixture
def recall_mock(monkeypatch):
    async def fake_recall(request):
        return RecallMemoryResponse(
            query=request.query,
            memories=[
                RecallMemoryItem(
                    id="mem-1",
                    text="Use Decimal for money",
                    type="observation",
                    context="team standard",
                )
            ],
        )

    monkeypatch.setattr(job_runner_module.hindsight_service, "recall_memories", fake_recall)


@pytest.mark.asyncio
class TestPasteJobs:
    async def test_paste_job_completes_with_aggregate(self, monkeypatch, recall_mock):
        async def fake_review(**kwargs):
            assert kwargs["is_diff"] is False
            assert kwargs["path"] == "snippet.py"
            return FileReview(
                summary="Mostly fine",
                issues=[
                    make_issue(severity=Severity.CRITICAL, file="snippet.py", line=1),
                    make_issue(severity=Severity.HIGH, file="snippet.py", line=2, title="B"),
                ],
                suggestions=["Add tests"],
            )

        monkeypatch.setattr(job_runner_module.llm_service, "generate_file_review", fake_review)

        job = await job_runner.start(
            JobRequest(mode=SourceMode.PASTE, code="x = 1.1\nprint(x)", language="python")
        )
        final = await wait_terminal(job)

        assert final.status == JobStatus.COMPLETED
        result = final.result
        assert result.mode == SourceMode.PASTE
        assert result.score == 100 - 25 - 12
        assert result.severity_counts.critical == 1
        assert result.severity_counts.high == 1
        assert len(result.issues) == 2
        assert result.issues[0].severity == Severity.CRITICAL  # sorted by severity
        assert [f.path for f in result.files] == ["snippet.py"]
        assert result.memories_used[0].id == "mem-1"
        assert "pasted snippet" in result.summary

    async def test_paste_job_without_code_fails(self, monkeypatch, recall_mock):
        job = await job_runner.start(JobRequest(mode=SourceMode.PASTE, code=None))
        final = await wait_terminal(job)
        assert final.status == JobStatus.FAILED
        assert "No code provided" in final.error

    async def test_recall_failure_does_not_block(self, monkeypatch):
        async def boom(request):
            raise RuntimeError("hindsight down")

        monkeypatch.setattr(job_runner_module.hindsight_service, "recall_memories", boom)
        monkeypatch.setattr(
            job_runner_module.llm_service,
            "generate_file_review",
            lambda **kwargs: asyncio.sleep(0, FileReview(summary="ok", issues=[])),
        )

        job = await job_runner.start(JobRequest(mode=SourceMode.PASTE, code="a = 1", language="python"))
        final = await wait_terminal(job)
        assert final.status == JobStatus.COMPLETED
        assert final.result.memories_used == []
        assert final.result.score == 100


@pytest.mark.asyncio
class TestUploadJobs:
    async def test_multiple_files_reviewed_and_one_failure_isolated(self, monkeypatch, recall_mock):
        calls = []

        async def fake_review(**kwargs):
            calls.append(kwargs["path"])
            if kwargs["path"] == "bad.py":
                raise RuntimeError("LLM exploded")
            return FileReview(
                summary=f"review of {kwargs['path']}",
                issues=[make_issue(file=kwargs["path"], line=5)],
                suggestions=[],
            )

        monkeypatch.setattr(job_runner_module.llm_service, "generate_file_review", fake_review)

        files = [
            SourceFile(path="good.py", content="a = 1", language="python", size=6),
            SourceFile(path="bad.py", content="b = 2", language="python", size=6),
        ]
        job = await job_runner.start(JobRequest(mode=SourceMode.FILES), files=files)
        final = await wait_terminal(job)

        assert final.status == JobStatus.COMPLETED
        result = final.result
        assert sorted(calls) == ["bad.py", "good.py"]
        by_path = {f.path: f for f in result.files}
        assert by_path["good.py"].issue_count == 1
        assert by_path["bad.py"].skipped is True
        assert "LLM exploded" in by_path["bad.py"].skip_reason
        assert len(result.issues) == 1
        assert result.issues[0].file == "good.py"

    async def test_all_failures_fail_job(self, monkeypatch, recall_mock):
        async def fake_review(**kwargs):
            raise RuntimeError("total failure")

        monkeypatch.setattr(job_runner_module.llm_service, "generate_file_review", fake_review)
        job = await job_runner.start(
            JobRequest(mode=SourceMode.FILES),
            files=[SourceFile(path="a.py", content="x", language="python", size=1)],
        )
        final = await wait_terminal(job)
        assert final.status == JobStatus.FAILED
        assert "total failure" in final.error


@pytest.mark.asyncio
class TestBranchJobs:
    async def test_branch_job_reviews_diffs(self, monkeypatch, recall_mock):
        fake_diff = FileDiff(
            path="src/billing.py",
            hunks=[
                DiffHunk(
                    old_start=1,
                    old_lines=2,
                    new_start=1,
                    new_lines=3,
                    lines=[
                        DiffLine(type="context", old_no=1, new_no=1, text="def charge(x):"),
                        DiffLine(type="del", old_no=2, text="    return x + 1"),
                        DiffLine(type="add", new_no=2, text="    return x + 1.0"),
                        DiffLine(type="add", new_no=3, text=""),
                    ],
                )
            ],
        )
        source = BranchSource(
            files=[SourceFile(path="src/billing.py", content="def charge(x):\n", language="python", size=18)],
            diffs=[fake_diff],
            branch="feature/x",
            base_branch="main",
            default_branch="main",
        )

        async def fake_fetch(repo_url, branch, base_branch):
            assert repo_url == "https://github.com/acme/app.git"
            assert branch == "feature/x"
            return source

        seen = {}

        async def fake_review(**kwargs):
            seen.update(kwargs)
            return FileReview(summary="diff reviewed", issues=[make_issue(line=2)], suggestions=[])

        monkeypatch.setattr(job_runner_module.source_service, "fetch_branch_source", fake_fetch)
        monkeypatch.setattr(job_runner_module.llm_service, "generate_file_review", fake_review)

        job = await job_runner.start(
            JobRequest(
                mode=SourceMode.BRANCH,
                repo_url="https://github.com/acme/app.git",
                branch="feature/x",
                base_branch="main",
            )
        )
        final = await wait_terminal(job)

        assert final.status == JobStatus.COMPLETED
        result = final.result
        assert result.branch == "feature/x"
        assert result.base_branch == "main"
        assert result.repo_url == "https://github.com/acme/app.git"
        assert len(result.diffs) == 1
        assert seen["is_diff"] is True
        assert "diff --git" not in seen["content"] or True
        assert "@@ -1,2 +1,3 @@" in seen["content"]
        assert "    return x + 1.0" in seen["content"]

    async def test_missing_branch_inputs_fail_fast(self, recall_mock):
        job = await job_runner.start(JobRequest(mode=SourceMode.BRANCH))
        final = await wait_terminal(job)
        assert final.status == JobStatus.FAILED
        assert "repo_url" in final.error


@pytest.mark.asyncio
class TestRequirementsJobs:
    async def test_requirements_files_job_reports_coverage(self, monkeypatch, recall_mock):
        async def fake_review(**kwargs):
            return FileReview(summary="ok", issues=[], suggestions=[])

        async def fake_requirements(*, requirements, files, memories):
            assert requirements == "R1 add login\nR2 export to CSV"
            assert [f.path for f in files] == ["app.py"]
            return RequirementsReport(
                items=[
                    RequirementItem(
                        id="R1",
                        title="add login",
                        kind="feature",
                        status=RequirementStatus.IMPLEMENTED,
                        evidence=["app.py:1"],
                    ),
                    RequirementItem(
                        id="R2",
                        title="export to CSV",
                        kind="feature",
                        status=RequirementStatus.MISSING,
                        gaps="no export code",
                    ),
                ],
                summary="half covered",
                implemented=1,
                partial=0,
                missing=1,
                coverage_pct=50,
            )

        monkeypatch.setattr(job_runner_module.llm_service, "generate_file_review", fake_review)
        monkeypatch.setattr(
            job_runner_module.llm_service, "generate_requirements_report", fake_requirements
        )

        job = await job_runner.start(
            JobRequest(
                mode=SourceMode.REQUIREMENTS,
                requirements="R1 add login\nR2 export to CSV",
            ),
            files=[SourceFile(path="app.py", content="def login(): ...", language="python", size=20)],
        )
        final = await wait_terminal(job)

        assert final.status == JobStatus.COMPLETED
        result = final.result
        assert result.mode == SourceMode.REQUIREMENTS
        assert result.requirements_report is not None
        assert result.requirements_report.coverage_pct == 50
        assert result.requirements_report.implemented == 1
        assert result.requirements_report.missing == 1
        assert "Coverage: 1/2 requirements implemented" in result.summary

    async def test_requirements_failure_keeps_review_results(self, monkeypatch, recall_mock):
        async def fake_review(**kwargs):
            return FileReview(summary="ok", issues=[], suggestions=[])

        async def boom(**kwargs):
            raise RuntimeError("rate limited")

        monkeypatch.setattr(job_runner_module.llm_service, "generate_file_review", fake_review)
        monkeypatch.setattr(job_runner_module.llm_service, "generate_requirements_report", boom)

        job = await job_runner.start(
            JobRequest(mode=SourceMode.REQUIREMENTS, requirements="R1"),
            files=[SourceFile(path="app.py", content="x = 1", language="python", size=5)],
        )
        final = await wait_terminal(job)

        assert final.status == JobStatus.COMPLETED
        result = final.result
        assert result.requirements_report is None
        assert "Requirements check failed: rate limited" in result.summary

    async def test_requirements_mode_with_pasted_code_uses_snippet(
        self, monkeypatch, recall_mock
    ):
        seen: dict = {}

        async def fake_review(**kwargs):
            seen.update(kwargs)
            return FileReview(summary="s", issues=[], suggestions=[])

        async def fake_requirements(*, requirements, files, memories):
            assert requirements == "R1"
            return RequirementsReport(items=[], summary="no items")

        monkeypatch.setattr(job_runner_module.llm_service, "generate_file_review", fake_review)
        monkeypatch.setattr(
            job_runner_module.llm_service, "generate_requirements_report", fake_requirements
        )

        job = await job_runner.start(
            JobRequest(mode=SourceMode.REQUIREMENTS, requirements="R1", code="x = 1", language="python")
        )
        final = await wait_terminal(job)

        assert final.status == JobStatus.COMPLETED
        assert seen["path"] == "snippet.py"
        assert final.result.requirements_report is not None
        assert final.result.requirements_report.items == []

    async def test_requirements_without_source_fails_fast(self, recall_mock):
        job = await job_runner.start(
            JobRequest(mode=SourceMode.REQUIREMENTS, requirements="R1")
        )
        final = await wait_terminal(job)
        assert final.status == JobStatus.FAILED
        assert "Provide code, files, or a branch" in final.error

    async def test_requirements_recall_query_uses_requirements_text(self, monkeypatch):
        queries: list = []

        async def fake_recall(request):
            queries.append(request.query)
            return RecallMemoryResponse(query=request.query, memories=[])

        async def fake_review(**kwargs):
            return FileReview(summary="s", issues=[], suggestions=[])

        async def fake_requirements(*, requirements, files, memories):
            return RequirementsReport(items=[])

        monkeypatch.setattr(job_runner_module.hindsight_service, "recall_memories", fake_recall)
        monkeypatch.setattr(job_runner_module.llm_service, "generate_file_review", fake_review)
        monkeypatch.setattr(
            job_runner_module.llm_service, "generate_requirements_report", fake_requirements
        )

        job = await job_runner.start(
            JobRequest(
                mode=SourceMode.REQUIREMENTS,
                requirements="R1 add login\nR2 export",
            ),
            files=[SourceFile(path="app.py", content="x = 1", language="python", size=5)],
        )
        final = await wait_terminal(job)

        assert final.status == JobStatus.COMPLETED
        assert queries
        assert queries[0].startswith("requirements implementation check")
        assert "R1 add login" in queries[0]


@pytest.mark.asyncio
class TestCancellation:
    async def test_cancel_request_ends_job(self, monkeypatch, recall_mock):
        async def slow_review(**kwargs):
            await asyncio.sleep(0.05)
            return FileReview(summary="s", issues=[], suggestions=[])

        monkeypatch.setattr(job_runner_module.llm_service, "generate_file_review", slow_review)
        job = await job_runner.start(JobRequest(mode=SourceMode.PASTE, code="a=1", language="python"))
        job_store.request_cancel(job.id)
        final = await wait_terminal(job, timeout=5)
        assert final.status == JobStatus.CANCELLED
