from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.job import JobProgress, JobStatus, SourceMode
from app.services.job_store import job_store

client = TestClient(app)


class TestCreateJobValidation:
    def test_paste_without_code_is_rejected(self):
        response = client.post("/api/jobs", json={"mode": "paste"})
        assert response.status_code == 400
        assert "No code provided" in response.json()["detail"]

    def test_paste_with_code_is_accepted(self):
        with patch("app.api.jobs.job_runner") as mock_runner:
            job = job_store.create(SourceMode.PASTE)
            mock_runner.start = AsyncMock(return_value=job)
            response = client.post(
                "/api/jobs",
                json={"mode": "paste", "code": "print(1)", "language": "python"},
            )
        assert response.status_code == 202
        body = response.json()
        assert body["job_id"] == job.id
        assert body["mode"] == "paste"

    def test_branch_with_bad_url_is_rejected(self):
        response = client.post(
            "/api/jobs",
            json={"mode": "branch", "repo_url": "file:///etc", "branch": "main"},
        )
        assert response.status_code == 400

    def test_branch_without_ref_is_rejected(self):
        response = client.post(
            "/api/jobs",
            json={"mode": "branch", "repo_url": "https://github.com/a/b.git"},
        )
        assert response.status_code == 400

    def test_files_mode_redirects_to_upload_endpoint(self):
        response = client.post("/api/jobs", json={"mode": "files"})
        assert response.status_code == 400
        assert "/api/jobs/upload" in response.json()["detail"]


class TestRequirementsValidation:
    def test_requirements_without_text_is_rejected(self):
        response = client.post("/api/jobs", json={"mode": "requirements", "code": "x = 1"})
        assert response.status_code == 400
        assert "No requirements provided" in response.json()["detail"]

    def test_requirements_without_source_is_rejected(self):
        response = client.post(
            "/api/jobs", json={"mode": "requirements", "requirements": "R1 do a thing"}
        )
        assert response.status_code == 400
        assert "Provide code, files, or a branch" in response.json()["detail"]

    def test_requirements_with_code_is_accepted(self):
        with patch("app.api.jobs.job_runner") as mock_runner:
            job = job_store.create(SourceMode.REQUIREMENTS)
            mock_runner.start = AsyncMock(return_value=job)
            response = client.post(
                "/api/jobs",
                json={
                    "mode": "requirements",
                    "requirements": "R1 do a thing",
                    "code": "print(1)",
                    "language": "python",
                },
            )
        assert response.status_code == 202
        body = response.json()
        assert body["job_id"] == job.id
        assert body["mode"] == "requirements"
        sent = mock_runner.start.call_args.args[0]
        assert sent.mode == SourceMode.REQUIREMENTS
        assert sent.requirements == "R1 do a thing"

    def test_requirements_branch_url_is_validated(self):
        response = client.post(
            "/api/jobs",
            json={
                "mode": "requirements",
                "requirements": "R1",
                "repo_url": "file:///etc",
                "branch": "main",
            },
        )
        assert response.status_code == 400

    def test_requirements_branch_without_ref_is_rejected(self):
        response = client.post(
            "/api/jobs",
            json={
                "mode": "requirements",
                "requirements": "R1",
                "repo_url": "https://github.com/a/b.git",
            },
        )
        assert response.status_code == 400

    def test_requirements_over_limit_is_rejected(self):
        response = client.post(
            "/api/jobs",
            json={
                "mode": "requirements",
                "requirements": "x" * 20_001,
                "code": "print(1)",
            },
        )
        assert response.status_code == 422


class TestUploadJob:
    def test_upload_requires_files(self):
        response = client.post("/api/jobs/upload")
        assert response.status_code == 422

    def test_upload_with_only_skipped_files_is_rejected(self):
        response = client.post(
            "/api/jobs/upload",
            files=[("files", ("README.md", b"# hello", "text/markdown"))],
        )
        assert response.status_code == 400
        assert "No reviewable files" in response.json()["detail"]

    def test_upload_starts_job_and_skips_are_tracked(self):
        with patch("app.api.jobs.job_runner") as mock_runner:
            job = job_store.create(SourceMode.FILES)
            mock_runner.start = AsyncMock(return_value=job)
            response = client.post(
                "/api/jobs/upload",
                data={"query": "security"},
                files=[
                    ("files", ("src/app.py", b"print(1)", "text/x-python")),
                    ("files", ("notes.md", b"# skip", "text/markdown")),
                ],
            )
        assert response.status_code == 202
        body = response.json()
        assert body["job_id"] == job.id
        assert body["mode"] == "files"
        call_kwargs = mock_runner.start.call_args.kwargs
        assert [f.path for f in call_kwargs["files"]] == ["src/app.py"]
        assert dict(call_kwargs["skipped"])["notes.md"] is not None

    def test_upload_paths_are_sanitised(self):
        with patch("app.api.jobs.job_runner") as mock_runner:
            job = job_store.create(SourceMode.FILES)
            mock_runner.start = AsyncMock(return_value=job)
            response = client.post(
                "/api/jobs/upload",
                files=[("files", ("../../etc/passwd.py", b"x = 1", "text/x-python"))],
            )
        assert response.status_code == 202
        uploaded = mock_runner.start.call_args.kwargs["files"]
        assert uploaded[0].path == "etc/passwd.py"

    def test_upload_with_requirements_sets_requirements_mode(self):
        with patch("app.api.jobs.job_runner") as mock_runner:
            job = job_store.create(SourceMode.REQUIREMENTS)
            mock_runner.start = AsyncMock(return_value=job)
            response = client.post(
                "/api/jobs/upload",
                data={"requirements": "  R1 do a thing  "},
                files=[("files", ("src/app.py", b"print(1)", "text/x-python"))],
            )
        assert response.status_code == 202
        assert response.json()["mode"] == "requirements"
        sent = mock_runner.start.call_args.args[0]
        assert sent.mode == SourceMode.REQUIREMENTS
        assert sent.requirements == "R1 do a thing"

    def test_upload_with_blank_requirements_stays_files_mode(self):
        with patch("app.api.jobs.job_runner") as mock_runner:
            job = job_store.create(SourceMode.FILES)
            mock_runner.start = AsyncMock(return_value=job)
            response = client.post(
                "/api/jobs/upload",
                data={"requirements": "   "},
                files=[("files", ("src/app.py", b"print(1)", "text/x-python"))],
            )
        assert response.status_code == 202
        assert response.json()["mode"] == "files"
        sent = mock_runner.start.call_args.args[0]
        assert sent.mode == SourceMode.FILES
        assert sent.requirements is None


class TestJobLifecycle:
    def test_get_unknown_job_404(self):
        assert client.get("/api/jobs/nope").status_code == 404

    def test_delete_unknown_job_404(self):
        assert client.delete("/api/jobs/nope").status_code == 404

    def test_get_returns_progress_and_result(self):
        job = job_store.create(SourceMode.PASTE)
        job_store.touch(job, status=JobStatus.REVIEWING, error=None)
        job_store.set_progress(job, step="Reviewing files", current=2, total=5, current_file="a.py")

        response = client.get(f"/api/jobs/{job.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "reviewing"
        assert body["progress"]["current"] == 2
        assert body["progress"]["total"] == 5
        assert body["progress"]["current_file"] == "a.py"

    def test_cancel_marks_terminal_job(self):
        job = job_store.create(SourceMode.PASTE)
        job_store.touch(job, status=JobStatus.COMPLETED)
        response = client.delete(f"/api/jobs/{job.id}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"  # already done, no change

    def test_cancel_running_job(self):
        job = job_store.create(SourceMode.PASTE)
        job_store.touch(job, status=JobStatus.REVIEWING)
        response = client.delete(f"/api/jobs/{job.id}")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


class TestBranchList:
    def test_lists_branches_with_default_flag(self):
        with patch(
            "app.api.jobs.source_service.list_remote_branches",
            AsyncMock(return_value=["develop", "main"]),
        ), patch(
            "app.api.jobs.source_service.remote_head_branch",
            AsyncMock(return_value="main"),
        ):
            response = client.get(
                "/api/branches", params={"repo_url": "https://github.com/a/b.git"}
            )
        assert response.status_code == 200
        branches = response.json()["branches"]
        assert {b["name"]: b["is_default"] for b in branches} == {
            "develop": False,
            "main": True,
        }

    def test_invalid_url_is_400(self):
        response = client.get("/api/branches", params={"repo_url": "file:///etc"})
        assert response.status_code == 400
