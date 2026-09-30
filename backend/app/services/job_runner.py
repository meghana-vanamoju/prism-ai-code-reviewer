import asyncio
from typing import Dict, List, Optional, Sequence, Tuple

from app.config import settings
from app.models.job import (
    FileSummary,
    JobRequest,
    JobStatus,
    ReviewResult,
    SeverityCounts,
    SkippedFile,
    SourceFile,
    SourceMode,
)
from app.models.memory import RecallMemoryRequest
from app.models.review import Issue, MemoryUsed, RequirementsReport, Severity
from app.services import source_service
from app.services.hindsight_service import hindsight_service
from app.services.job_store import Job, job_store
from app.services.llm_service import llm_service

SEVERITY_PENALTIES: Dict[Severity, int] = {
    Severity.CRITICAL: 25,
    Severity.HIGH: 12,
    Severity.MEDIUM: 6,
    Severity.LOW: 3,
    Severity.SUGGESTION: 1,
}

SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.SUGGESTION: 4,
}

EXT_BY_LANGUAGE = {
    "python": "py",
    "javascript": "js",
    "typescript": "ts",
    "go": "go",
    "rust": "rs",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "csharp": "cs",
    "ruby": "rb",
    "php": "php",
    "swift": "swift",
    "kotlin": "kt",
    "shell": "sh",
    "sql": "sql",
    "html": "html",
    "css": "css",
}


class JobCancelled(Exception):
    pass


class JobRunner:
    async def start(
        self,
        request: JobRequest,
        files: Optional[Sequence[SourceFile]] = None,
        skipped: Optional[Sequence[Tuple[str, str]]] = None,
    ) -> Job:
        job = job_store.create(request.mode)
        if skipped:
            job.skipped = [SkippedFile(path=p, reason=r) for p, r in skipped]
        task = asyncio.create_task(self._run(job, request, files))
        job.handle = task
        return job

    async def _run(
        self,
        job: Job,
        request: JobRequest,
        upload_files: Optional[Sequence[SourceFile]],
    ) -> None:
        try:
            result = await self._execute(job, request, upload_files)
            if job.cancel_requested:
                job_store.cancel(job)
                return
            job_store.touch(job, status=JobStatus.COMPLETED, result=result, error=None)
        except JobCancelled:
            job_store.cancel(job)
        except source_service.SourceError as e:
            job_store.touch(job, status=JobStatus.FAILED, error=str(e))
        except ValueError as e:
            job_store.touch(job, status=JobStatus.FAILED, error=str(e))
        except Exception as e:  # noqa: BLE001 - job must always reach a terminal state
            job_store.touch(job, status=JobStatus.FAILED, error=f"Review failed: {e}")

    async def _execute(
        self,
        job: Job,
        request: JobRequest,
        upload_files: Optional[Sequence[SourceFile]],
    ) -> ReviewResult:
        # ---- 1. Fetch source ------------------------------------------------
        job_store.touch(job, status=JobStatus.FETCHING)
        job_store.set_progress(job, step="Fetching source", current=0, total=0, current_file=None)
        await self._maybe_cancel(job)

        branch: Optional[str] = None
        base_branch: Optional[str] = None
        repo_url: Optional[str] = None
        diffs = []
        files: List[SourceFile]

        wants_branch = job.mode == SourceMode.BRANCH or (
            job.mode == SourceMode.REQUIREMENTS
            and not upload_files
            and (request.repo_url or request.branch)
        )
        if wants_branch:
            if not request.repo_url or not request.branch:
                raise ValueError("Both repo_url and branch are required for branch review.")
            source = await source_service.fetch_branch_source(
                request.repo_url, request.branch, request.base_branch
            )
            files = source.files
            diffs = source.diffs
            branch = source.branch
            base_branch = source.base_branch
            repo_url = request.repo_url
            job.skipped = [SkippedFile(path=p, reason=r) for p, r in source.skipped]
        elif upload_files or job.mode == SourceMode.FILES:
            if not upload_files:
                raise ValueError("No files were uploaded for review.")
            files = list(upload_files)
        else:
            # Paste-style source: paste mode, or requirements mode with pasted code.
            code_text = request.code or ""
            if not code_text.strip():
                if job.mode == SourceMode.REQUIREMENTS:
                    raise ValueError(
                        "Provide code, files, or a branch to check requirements against."
                    )
                raise ValueError("No code provided for review.")
            language = (request.language or "other").strip().lower() or "other"
            ext = EXT_BY_LANGUAGE.get(language, "txt")
            files = [
                SourceFile(
                    path=f"snippet.{ext}",
                    content=code_text,
                    language=language if language in EXT_BY_LANGUAGE else "other",
                    size=len(code_text),
                )
            ]

        if not files:
            raise ValueError("No reviewable files found in the submitted source.")
        await self._maybe_cancel(job)

        # ---- 2. Recall team memories ---------------------------------------
        job_store.touch(job, status=JobStatus.RECALLING)
        job_store.set_progress(job, step="Recalling team memories", current=0, total=len(files))
        memories = await self._recall_memories(request, files, branch)
        await self._maybe_cancel(job)

        # ---- 3. Review each file -------------------------------------------
        job_store.touch(job, status=JobStatus.REVIEWING)
        job_store.set_progress(
            job, step="Reviewing files", current=0, total=len(files), current_file=files[0].path
        )

        is_diff = job.mode == SourceMode.BRANCH
        diff_by_path = {d.path: d for d in diffs}
        semaphore = asyncio.Semaphore(max(1, settings.review_concurrency))
        completed = 0
        results: Dict[str, Tuple[List[Issue], List[str], str]] = {}
        failures: Dict[str, str] = {}

        async def review_one(source_file: SourceFile) -> None:
            nonlocal completed
            if job.cancel_requested:
                raise JobCancelled()
            async with semaphore:
                if job.cancel_requested:
                    raise JobCancelled()
                try:
                    if is_diff:
                        entry = diff_by_path.get(source_file.path)
                        content = source_service.diff_to_text(entry) if entry else source_file.content
                        review = await llm_service.generate_file_review(
                            path=source_file.path,
                            content=content,
                            language=source_file.language,
                            memories=memories,
                            focus=request.query,
                            is_diff=True,
                        )
                    else:
                        review = await llm_service.generate_file_review(
                            path=source_file.path,
                            content=source_file.content,
                            language=source_file.language,
                            memories=memories,
                            focus=request.query,
                            is_diff=False,
                        )
                    results[source_file.path] = (review.issues, review.suggestions, review.summary)
                except JobCancelled:
                    raise
                except Exception as e:  # keep reviewing other files
                    failures[source_file.path] = str(e)
                finally:
                    completed += 1
                    job_store.set_progress(
                        job,
                        step="Reviewing files",
                        current=completed,
                        total=len(files),
                        current_file=source_file.path,
                    )

        await asyncio.gather(*(review_one(f) for f in files))

        if not results and failures:
            raise RuntimeError(next(iter(failures.values())))

        await self._maybe_cancel(job)

        # ---- 4. Aggregate ----------------------------------------------------
        issues: List[Issue] = []
        suggestions: List[str] = []
        file_summaries: List[FileSummary] = []
        summaries: List[Tuple[str, str]] = []

        for source_file in files:
            if source_file.path in failures:
                file_summaries.append(
                    FileSummary(
                        path=source_file.path,
                        language=source_file.language,
                        issue_count=0,
                        skipped=True,
                        skip_reason=failures[source_file.path],
                    )
                )
                continue
            file_issues, file_suggestions, file_summary = results.get(
                source_file.path, ([], [], "")
            )
            issues.extend(file_issues)
            for suggestion in file_suggestions:
                if suggestion not in suggestions:
                    suggestions.append(suggestion)
            if file_summary:
                summaries.append((source_file.path, file_summary))
            content_limit = 20_000
            content = source_file.content
            truncated = len(content) > content_limit
            if truncated:
                content = content[:content_limit]
            file_summaries.append(
                FileSummary(
                    path=source_file.path,
                    language=source_file.language,
                    issue_count=len(file_issues),
                    content=content,
                    truncated=truncated,
                )
            )

        issues.sort(
            key=lambda i: (
                SEVERITY_ORDER.get(i.severity, 9),
                i.file or "",
                i.line or 0,
            )
        )

        counts = SeverityCounts(
            critical=sum(1 for i in issues if i.severity == Severity.CRITICAL),
            high=sum(1 for i in issues if i.severity == Severity.HIGH),
            medium=sum(1 for i in issues if i.severity == Severity.MEDIUM),
            low=sum(1 for i in issues if i.severity == Severity.LOW),
            suggestion=sum(1 for i in issues if i.severity == Severity.SUGGESTION),
        )
        score = max(
            0,
            100
            - sum(count * SEVERITY_PENALTIES[sev] for sev, count in (
                (Severity.CRITICAL, counts.critical),
                (Severity.HIGH, counts.high),
                (Severity.MEDIUM, counts.medium),
                (Severity.LOW, counts.low),
                (Severity.SUGGESTION, counts.suggestion),
            )),
        )

        # ---- 5. Requirements traceability ----------------------------------
        requirements_report: Optional[RequirementsReport] = None
        requirements_error: Optional[str] = None
        req_text = (request.requirements or "").strip()
        if req_text:
            job_store.set_progress(
                job, step="Checking requirements", current=0, total=0, current_file=None
            )
            await self._maybe_cancel(job)
            try:
                requirements_report = await llm_service.generate_requirements_report(
                    requirements=req_text,
                    files=files,
                    memories=memories,
                )
            except JobCancelled:
                raise
            except Exception as e:  # noqa: BLE001 - keep the code review results
                requirements_error = str(e)

        return ReviewResult(
            summary=self._compose_summary(
                job.mode,
                files,
                issues,
                summaries,
                branch,
                base_branch,
                requirements_report=requirements_report,
                requirements_error=requirements_error,
            ),
            score=score,
            severity_counts=counts,
            issues=issues,
            suggestions=suggestions,
            files=file_summaries,
            diffs=diffs,
            memories_used=memories,
            requirements_report=requirements_report,
            model_used=settings.groq_model,
            mode=job.mode,
            repo_url=repo_url,
            branch=branch,
            base_branch=base_branch,
        )

    async def _recall_memories(
        self,
        request: JobRequest,
        files: Sequence[SourceFile],
        branch: Optional[str],
    ) -> List[MemoryUsed]:
        query = request.query or self._build_recall_query(
            files, branch, request.requirements
        )
        try:
            response = await hindsight_service.recall_memories(
                RecallMemoryRequest(
                    query=query,
                    bank_id=request.bank_id or settings.hindsight_bank_id,
                    budget=request.recall_budget,
                    max_tokens=4096,
                )
            )
        except Exception:
            return []  # memory outage must not block the review

        limit = min(request.max_memories, settings.review_max_memories)
        return [
            MemoryUsed(
                id=m.id,
                text=m.text,
                type=m.type,
                context=m.context,
                metadata=m.metadata,
            )
            for m in response.memories[:limit]
        ]

    def _build_recall_query(
        self,
        files: Sequence[SourceFile],
        branch: Optional[str],
        requirements: Optional[str] = None,
    ) -> str:
        if requirements and requirements.strip():
            first_line = requirements.strip().splitlines()[0][:200]
            return f"requirements implementation check: {first_line}"
        paths = ", ".join(f.path for f in files[:8])
        prefix = f"changes on branch {branch}" if branch else "code review standards and best practices for"
        return f"{prefix}: {paths}"

    def _compose_summary(
        self,
        mode: SourceMode,
        files: Sequence[SourceFile],
        issues: Sequence[Issue],
        summaries: Sequence[Tuple[str, str]],
        branch: Optional[str],
        base_branch: Optional[str],
        requirements_report: Optional[RequirementsReport] = None,
        requirements_error: Optional[str] = None,
    ) -> str:
        label = {
            SourceMode.PASTE: "pasted snippet",
            SourceMode.FILES: f"{len(files)} uploaded file{'s' if len(files) != 1 else ''}",
            SourceMode.BRANCH: (
                f"branch `{branch}` vs `{base_branch}`" if branch else "branch changes"
            ),
            SourceMode.REQUIREMENTS: (
                f"{len(files)} file{'s' if len(files) != 1 else ''} checked against requirements"
            ),
        }[mode]

        counts: Dict[Severity, int] = {}
        for issue in issues:
            counts[issue.severity] = counts.get(issue.severity, 0) + 1
        breakdown = ", ".join(
            f"{counts[sev]} {sev.value}" for sev in SEVERITY_ORDER if counts.get(sev)
        )

        if not issues:
            head = f"Reviewed {label}: no issues found. Code aligns with known team standards."
        else:
            head = (
                f"Reviewed {label}: {len(issues)} issue{'s' if len(issues) != 1 else ''} found"
                + (f" ({breakdown})" if breakdown else "")
                + "."
            )

        notable = [f"{path} — {text}" for path, text in summaries if text][:4]
        if notable:
            head += " " + " ".join(notable)

        if requirements_report is not None and requirements_report.items:
            head += (
                f" Coverage: {requirements_report.implemented}/{len(requirements_report.items)} "
                f"requirements implemented ({requirements_report.partial} partial, "
                f"{requirements_report.missing} missing)."
            )
        elif requirements_error:
            head += f" Requirements check failed: {requirements_error}."
        return head

    async def _maybe_cancel(self, job: Job) -> None:
        if job.cancel_requested:
            raise JobCancelled()


job_runner = JobRunner()
