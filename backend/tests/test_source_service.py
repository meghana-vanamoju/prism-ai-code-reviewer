import pytest

from pathlib import Path

from app.services.source_service import (
    SourceError,
    diff_to_text,
    ingest_entries,
    language_for_path,
    parse_unified_diff,
    skip_reason_for,
    validate_ref,
    validate_repo_url,
)

SAMPLE_DIFF = """diff --git a/src/billing.py a/src/billing.py
index 1111111..2222222 100644
--- a/src/billing.py
+++ b/src/billing.py
@@ -10,7 +10,8 @@ def charge(amount):
     tax = amount * 0.2
-    total = amount + tax
+    # use Decimal for money
+    total = round(amount + tax, 2)
     return total
"""


class TestLanguageDetection:
    @pytest.mark.parametrize(
        "path,expected",
        [
            ("app/main.py", "python"),
            ("src/index.ts", "typescript"),
            ("src/App.tsx", "typescript"),
            ("cmd/server.go", "go"),
            ("lib.rs", "rust"),
            ("unknown.xyz", "other"),
        ],
    )
    def test_language_for_path(self, path, expected):
        assert language_for_path(path) == expected


class TestSkipRules:
    @pytest.mark.parametrize(
        "path",
        [
            "node_modules/left-pad/index.js",
            "pkg/package-lock.json",
            "dist/bundle.js",
            "docs/README.md",
            "assets/logo.png",
            "__pycache__/mod.pyc",
            "vendor/lib.go",
            "src/app.min.js",
        ],
    )
    def test_skips_non_reviewable_paths(self, path):
        assert skip_reason_for(path) is not None

    @pytest.mark.parametrize(
        "path",
        ["src/app.py", "web/index.tsx", "svc/handler.go", ".github/workflows/ci.yml"],
    )
    def test_keeps_reviewable_paths(self, path):
        assert skip_reason_for(path) is None

    @pytest.mark.parametrize(
        "path",
        ["Makefile", "docker/Dockerfile", "Rakefile", "Procfile", "Gemfile"],
    )
    def test_keeps_well_known_extensionless_files(self, path):
        assert skip_reason_for(path) is None

    @pytest.mark.parametrize("path", ["README", "LICENSE", ".eslintrc"])
    def test_still_skips_other_extensionless_files(self, path):
        assert skip_reason_for(path) is not None


class TestIngestEntries:
    def test_keeps_code_and_reports_skips(self):
        outcome = ingest_entries(
            [
                ("app.py", b"print('hi')\n"),
                ("README.md", b"# docs"),
                ("node_modules/x/y.js", b"module.exports = 1"),
            ]
        )
        assert [f.path for f in outcome.files] == ["app.py"]
        assert outcome.files[0].language == "python"
        assert dict(outcome.skipped)["README.md"] is not None
        assert any(p.startswith("node_modules") for p, _ in outcome.skipped)

    def test_enforces_max_files(self):
        entries = [(f"file{i}.py", b"x = 1\n") for i in range(5)]
        outcome = ingest_entries(entries, max_files=2)
        assert len(outcome.files) == 2
        assert len(outcome.skipped) == 3

    def test_enforces_size_limits(self):
        big = b"a" * 1000
        outcome = ingest_entries([("big.py", big)], max_file_bytes=500)
        assert not outcome.files
        assert "larger than" in outcome.skipped[0][1]

    def test_enforces_total_budget(self):
        outcome = ingest_entries(
            [("a.py", b"x" * 400), ("b.py", b"y" * 400)],
            max_total_bytes=600,
        )
        assert len(outcome.files) == 1
        assert outcome.skipped[0][0] == "b.py"

    def test_rejects_binary_content(self):
        outcome = ingest_entries([("bin.py", b"print(\x00\x01\x02fake)")])
        assert not outcome.files
        assert "binary" in outcome.skipped[0][1]


class TestUnifiedDiffParsing:
    def test_parses_hunks_and_line_numbers(self):
        diffs = parse_unified_diff(SAMPLE_DIFF)
        assert len(diffs) == 1
        entry = diffs[0]
        assert entry.path == "src/billing.py"
        assert len(entry.hunks) == 1
        hunk = entry.hunks[0]
        assert hunk.old_start == 10
        assert hunk.new_start == 10
        types = [line.type for line in hunk.lines]
        assert "add" in types and "del" in types and "context" in types
        added = next(line for line in hunk.lines if line.type == "add")
        assert added.new_no is not None
        deleted = next(line for line in hunk.lines if line.type == "del")
        assert deleted.old_no is not None

    def test_parses_new_file_diff(self):
        diff = """diff --git a/new.py b/new.py
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+def hello():
+    return "hi"
"""
        diffs = parse_unified_diff(diff)
        assert len(diffs) == 1
        assert diffs[0].path == "new.py"
        assert all(line.type == "add" for line in diffs[0].hunks[0].lines)

    def test_empty_output_returns_nothing(self):
        assert parse_unified_diff("") == []

    def test_diff_to_text_renders_unified_form(self):
        diffs = parse_unified_diff(SAMPLE_DIFF)
        text = diff_to_text(diffs[0])
        assert text.startswith("--- a/src/billing.py")
        assert "+++ b/src/billing.py" in text
        assert "@@ -10,7 +10,8 @@" in text
        assert "+    total = round(amount + tax, 2)" in text
        assert "-    total = amount + tax" in text


class TestValidation:
    @pytest.mark.parametrize("url", ["https://github.com/owner/repo.git", "git@github.com:owner/repo.git"])
    def test_accepts_valid_urls(self, url):
        assert validate_repo_url(url) == url

    @pytest.mark.parametrize(
        "url",
        ["", "/local/path", "file:///etc/passwd", "https://example.com/a b", "javascript:alert(1)"],
    )
    def test_rejects_invalid_urls(self, url):
        with pytest.raises(SourceError):
            validate_repo_url(url)

    @pytest.mark.parametrize("ref", ["main", "develop", "feature/login", "v1.2.3"])
    def test_accepts_valid_refs(self, ref):
        assert validate_ref(ref, "branch") == ref

    @pytest.mark.parametrize("ref", ["", "-rf", "a..b", "has space", "ends/", "../etc"])
    def test_rejects_invalid_refs(self, ref):
        with pytest.raises(SourceError):
            validate_ref(ref, "branch")


BRANCH_DIFF = """diff --git a/keep.py b/keep.py
index 1111111..2222222 100644
--- a/keep.py
+++ b/keep.py
@@ -1,2 +1,2 @@
-def old():
+def new():
    return 1
diff --git a/removed.py b/removed.py
deleted file mode 100644
index 3333333..0000000
--- a/removed.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def legacy():
-    pass
"""

BRANCH_NAME_STATUS = "M\tkeep.py\nD\tremoved.py\n"


class TestFetchBranchSource:
    @pytest.mark.asyncio
    async def test_deleted_files_are_kept_with_empty_content(self, monkeypatch, tmp_path):
        import app.services.source_service as ss

        async def fake_run_git(args, cwd=None, timeout=None):  # noqa: ANN001
            if args[0] == "clone":
                target = Path(args[-1])
                target.mkdir(parents=True, exist_ok=True)
                (target / "keep.py").write_text("def new():\n    return 1\n")
                return ""
            if args[0] == "fetch":
                return ""
            if args[:2] == ["diff", "--name-status"]:
                return BRANCH_NAME_STATUS
            if args[0] == "diff":
                return BRANCH_DIFF
            raise AssertionError(f"unexpected git call: {args}")

        async def fake_head(url):  # noqa: ANN001
            return "main"

        monkeypatch.setattr(ss, "_run_git", fake_run_git)
        monkeypatch.setattr(ss, "remote_head_branch", fake_head)

        source = await ss.fetch_branch_source(
            "https://github.com/example/repo.git", "feature", "main"
        )

        paths = [f.path for f in source.files]
        assert "keep.py" in paths
        assert "removed.py" in paths

        by_path = {f.path: f for f in source.files}
        assert by_path["keep.py"].content.startswith("def new()")
        assert by_path["removed.py"].content == ""
        assert by_path["removed.py"].language == "python"

        diff_paths = [d.path for d in source.diffs]
        assert "keep.py" in diff_paths
        assert "removed.py" in diff_paths
        assert source.branch == "feature"
        assert source.base_branch == "main"
