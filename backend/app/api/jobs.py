from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.models.job import (
    BranchInfo,
    BranchListResponse,
    JobRequest,
    JobResponse,
    SkippedFile,
    SourceMode,
)
from app.services import source_service
from app.services.job_runner import job_runner
from app.services.job_store import job_store

router = APIRouter(prefix="/api", tags=["jobs"])


def _safe_upload_path(filename: Optional[str]) -> str:
    raw = (filename or "upload.txt").replace("\\", "/")
    parts = [p for p in raw.split("/") if p not in ("", ".", "..")]
    if not parts:
        return "upload.txt"
    return "/".join(parts)


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(request: JobRequest):
    if request.mode == SourceMode.PASTE:
        if not (request.code or "").strip():
            raise HTTPException(status_code=400, detail="No code provided for review.")
    elif request.mode == SourceMode.BRANCH:
        try:
            source_service.validate_repo_url(request.repo_url or "")
            source_service.validate_ref(request.branch or "", "branch")
            if request.base_branch:
                source_service.validate_ref(request.base_branch, "base branch")
        except source_service.SourceError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif request.mode == SourceMode.REQUIREMENTS:
        if not (request.requirements or "").strip():
            raise HTTPException(status_code=400, detail="No requirements provided.")
        if request.repo_url or request.branch:
            try:
                source_service.validate_repo_url(request.repo_url or "")
                source_service.validate_ref(request.branch or "", "branch")
                if request.base_branch:
                    source_service.validate_ref(request.base_branch, "base branch")
            except source_service.SourceError as e:
                raise HTTPException(status_code=400, detail=str(e))
        elif not (request.code or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Provide code, files, or a branch to check requirements against.",
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="mode=files requires the multipart upload endpoint /api/jobs/upload",
        )

    job = await job_runner.start(request)
    return job_store.to_response(job)


@router.post("/jobs/upload", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_job(
    files: List[UploadFile] = File(..., description="Files to review (path via filename)"),
    query: Optional[str] = Form(None),
    requirements: Optional[str] = Form(None),
):
    entries = []
    for upload in files:
        path = _safe_upload_path(upload.filename)
        try:
            data = await upload.read()
        except Exception:
            continue
        entries.append((path, data))

    if not entries:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    outcome = source_service.ingest_entries(entries)
    if not outcome.files:
        reasons = "; ".join(f"{p}: {r}" for p, r in outcome.skipped[:5])
        raise HTTPException(
            status_code=400,
            detail=f"No reviewable files in the upload. {reasons}",
        )

    req_text = (requirements or "").strip()
    request = JobRequest(
        mode=SourceMode.REQUIREMENTS if req_text else SourceMode.FILES,
        query=(query or "").strip() or None,
        requirements=req_text or None,
    )
    job = await job_runner.start(request, files=outcome.files, skipped=outcome.skipped)
    return job_store.to_response(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job_store.purge_expired()
    return job_store.to_response(job)


@router.delete("/jobs/{job_id}", response_model=JobResponse)
async def cancel_job(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job_store.request_cancel(job_id)
    handle = job.handle
    if not job.is_terminal:
        if handle is None:
            # No task attached (or it never started): mark terminal directly.
            job_store.cancel(job)
        else:
            cancel = getattr(handle, "cancel", None)
            if callable(cancel):
                try:
                    cancel()
                except Exception:
                    pass
            job_store.cancel(job)
    return job_store.to_response(job)


@router.get("/branches", response_model=BranchListResponse)
async def list_branches(repo_url: str = Query(..., min_length=1, max_length=500)):
    try:
        branches = await source_service.list_remote_branches(repo_url)
    except source_service.SourceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to list branches: {e}")

    default = await source_service.remote_head_branch(repo_url.strip())
    return BranchListResponse(
        repo_url=repo_url,
        branches=[BranchInfo(name=b, is_default=(b == default)) for b in branches],
    )
