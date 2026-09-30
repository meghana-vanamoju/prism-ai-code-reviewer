import asyncio
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.config import settings
from app.models.job import DiffHunk, DiffLine, FileDiff, SourceFile

GIT_TIMEOUT = settings.git_clone_timeout


class SourceError(Exception):
    """User-facing error while ingesting a review source."""


LANGUAGE_BY_EXT: Dict[str, str] = {
    "py": "python",
    "pyi": "python",
    "js": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "go": "go",
    "rs": "rust",
    "java": "java",
    "c": "c",
    "h": "c",
    "cpp": "cpp",
    "cc": "cpp",
    "hpp": "cpp",
    "cxx": "cpp",
    "cs": "csharp",
    "rb": "ruby",
    "php": "php",
    "swift": "swift",
    "kt": "kotlin",
    "kts": "kotlin",
    "scala": "scala",
    "sh": "shell",
    "bash": "shell",
    "zsh": "shell",
    "sql": "sql",
    "html": "html",
    "htm": "html",
    "css": "css",
    "scss": "scss",
    "less": "less",
    "vue": "vue",
    "svelte": "svelte",
    "json": "json",
    "yml": "yaml",
    "yaml": "yaml",
    "toml": "toml",
    "xml": "xml",
    "graphql": "graphql",
    "proto": "protobuf",
    "dart": "dart",
    "lua": "lua",
    "r": "r",
    "jl": "julia",
    "ex": "elixir",
    "exs": "elixir",
    "erl": "erlang",
    "hs": "haskell",
    "clj": "clojure",
    "zig": "zig",
    "vim": "vim",
}

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "out",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
    ".nuxt",
    ".cache",
    "vendor",
    "docs",
    "target",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".eggs",
    ".gradle",
    "bower_components",
    ".terraform",
    "Pods",
}

SKIP_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "cargo.lock",
    "gemfile.lock",
    "composer.lock",
    "pipfile.lock",
    "uv.lock",
    ".DS_Store",
    "go.sum",
}

# Extensionless files that are still plain-text, reviewable build/config entry points.
EXTENSIONLESS_FILES = {
    "makefile",
    "gnumakefile",
    "dockerfile",
    "rakefile",
    "gemfile",
    "procfile",
    "jenkinsfile",
    "vagrantfile",
    "justfile",
}

SKIP_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".bmp",
    ".avif",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".jar",
    ".war",
    ".class",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".dat",
    ".db",
    ".sqlite",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".mp3",
    ".mp4",
    ".mov",
    ".avi",
    ".webm",
    ".pyc",
    ".pyo",
    ".pyd",
    ".o",
    ".a",
    ".obj",
    ".wasm",
    ".ico",
    ".lock",
    ".md",
    ".markdown",
    ".rst",
    ".txt",
    ".csv",
    ".tsv",
    ".po",
    ".pot",
    ".min.js",
    ".min.css",
    ".map",
}

_CODE_EXTS = {
    ext
    for ext in LANGUAGE_BY_EXT
    if ext not in {"json", "yml", "yaml", "toml", "xml"}
}


def language_for_path(path: str) -> str:
    name = PurePosixPath(path).name.lower()
    for suffix in (".min.js", ".min.css"):
        if name.endswith(suffix):
            return "other"
    ext = Path(name).suffix.lstrip(".")
    return LANGUAGE_BY_EXT.get(ext, "other")


def skip_reason_for(path: str) -> Optional[str]:
    """Return a human-readable reason to skip the path, or None to keep it."""
    posix = PurePosixPath(path.replace("\\", "/"))
    name = posix.name

    parts = [p.lower() for p in posix.parts[:-1]]
    for part in parts:
        if part in SKIP_DIRS or part.lower() in {d.lower() for d in SKIP_DIRS}:
            return f"ignored directory ({part})"

    if name.lower() in SKIP_FILES:
        return "lock or generated file"

    lower = name.lower()
    for suffix in (".min.js", ".min.css"):
        if lower.endswith(suffix):
            return "minified file"

    ext = Path(lower).suffix
    if ext in SKIP_EXTS:
        if ext in {".md", ".markdown", ".rst", ".txt"}:
            return "documentation file"
        if ext == ".lock":
            return "lock file"
        return f"binary or non-code file ({ext})"

    if ext and ext.lstrip(".") not in LANGUAGE_BY_EXT:
        return f"unsupported file type ({ext})"

    if not ext:
        if name.lower() in EXTENSIONLESS_FILES:
            return None
        return "no file extension"

    return None


def _is_probably_binary(sample: bytes) -> bool:
    if b"\x00" in sample:
        return True
    if not sample:
        return False
    text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
    nontext = sample.translate(None, text_chars)
    return len(nontext) / len(sample) > 0.30


@dataclass
class IngestOutcome:
    files: List[SourceFile] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)


def ingest_entries(
    entries: Sequence[Tuple[str, bytes]],
    *,
    max_files: Optional[int] = None,
    max_file_bytes: Optional[int] = None,
    max_total_bytes: Optional[int] = None,
) -> IngestOutcome:
    """Turn (path, raw bytes) pairs into validated SourceFiles with skip accounting."""
    max_files = settings.review_max_files if max_files is None else max_files
    max_file_bytes = settings.review_max_file_bytes if max_file_bytes is None else max_file_bytes
    max_total_bytes = settings.review_max_total_bytes if max_total_bytes is None else max_total_bytes

    outcome = IngestOutcome()
    total = 0

    for path, raw in entries:
        clean = path.replace("\\", "/").lstrip("./")
        if not clean:
            continue

        reason = skip_reason_for(clean)
        if reason:
            outcome.skipped.append((clean, reason))
            continue

        if len(raw) > max_file_bytes:
            outcome.skipped.append((clean, f"larger than {max_file_bytes // 1000} KB"))
            continue

        if total + len(raw) > max_total_bytes:
            outcome.skipped.append((clean, "total upload size limit reached"))
            continue

        if _is_probably_binary(raw[:4096]):
            outcome.skipped.append((clean, "binary content"))
            continue

        if len(outcome.files) >= max_files:
            outcome.skipped.append((clean, f"file limit reached ({max_files})"))
            continue

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            outcome.skipped.append((clean, "not valid UTF-8 text"))
            continue

        outcome.files.append(
            SourceFile(
                path=clean,
                content=content,
                language=language_for_path(clean),
                size=len(raw),
            )
        )
        total += len(raw)

    return outcome


def ingest_paths(paths: Iterable[str], base_dir: Path) -> Tuple[List[Tuple[str, bytes]], List[Tuple[str, str]]]:
    """Read relative paths from a directory, returning (entries, skipped)."""
    entries: List[Tuple[str, bytes]] = []
    skipped: List[Tuple[str, str]] = []
    for rel in paths:
        full = (base_dir / rel).resolve()
        try:
            full.relative_to(base_dir.resolve())
        except ValueError:
            skipped.append((rel, "outside upload directory"))
            continue
        if not full.is_file():
            continue
        try:
            entries.append((rel, full.read_bytes()))
        except OSError as e:
            skipped.append((rel, f"unreadable: {e}"))
    return entries, skipped


# ---------------------------------------------------------------------------
# Git branch ingestion
# ---------------------------------------------------------------------------

_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,254}$")
_SAFE_URL = re.compile(r"^(https?|git|ssh)://[^\s'\"|&;]+$|^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:[A-Za-z0-9._\-/]+$")
_DIFF_GIT_RE = re.compile(r"^diff --git a/(.*?) b/(.*)$")
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


def validate_repo_url(repo_url: str) -> str:
    url = (repo_url or "").strip()
    if not url:
        raise SourceError("Repository URL is required.")
    if len(url) > 500:
        raise SourceError("Repository URL is too long.")
    if url.startswith("file://") or url.startswith("/"):
        raise SourceError("Only remote repository URLs are supported (https:// or git@).")
    if not _SAFE_URL.match(url):
        raise SourceError("Invalid repository URL. Use https://host/owner/repo.git or git@host:owner/repo.git.")
    return url


def validate_ref(name: str, label: str) -> str:
    ref = (name or "").strip()
    if not ref:
        raise SourceError(f"{label} is required.")
    if not _SAFE_REF.match(ref) or ".." in ref or ref.endswith("/") or ref.endswith("."):
        raise SourceError(f"Invalid {label}: {ref!r}")
    return ref


async def _run_git(args: Sequence[str], *, cwd: Optional[str] = None, timeout: int = GIT_TIMEOUT) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "true", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": tempfile.gettempdir()},
        )
    except FileNotFoundError as e:
        raise SourceError("git is not installed on the server.") from e

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise SourceError(f"git command timed out after {timeout}s: {' '.join(args[:3])}")

    if proc.returncode != 0:
        detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
        raise SourceError(f"git failed: {detail.splitlines()[0] if detail else 'unknown error'}")

    return stdout.decode("utf-8", errors="replace")


async def remote_head_branch(repo_url: str) -> Optional[str]:
    """Return the default branch name advertised by the remote, if detectable."""
    try:
        out = await _run_git(["ls-remote", "--symref", repo_url, "HEAD"], timeout=30)
    except SourceError:
        return None
    match = re.search(r"ref:\s+refs/heads/(\S+)\s+HEAD", out)
    return match.group(1) if match else None


async def list_remote_branches(repo_url: str) -> List[str]:
    url = validate_repo_url(repo_url)
    out = await _run_git(["ls-remote", "--heads", url], timeout=45)
    names = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or not parts[1].startswith("refs/heads/"):
            continue
        name = parts[1][len("refs/heads/"):]
        if _SAFE_REF.match(name):
            names.append(name)
    if not names:
        raise SourceError("No branches found (private repository or bad URL?).")
    return sorted(names)


@dataclass
class BranchSource:
    files: List[SourceFile]
    diffs: List[FileDiff]
    branch: str
    base_branch: str
    default_branch: Optional[str]
    skipped: List[Tuple[str, str]] = field(default_factory=list)


async def fetch_branch_source(repo_url: str, branch: str, base_branch: Optional[str]) -> BranchSource:
    """Shallow-clone `branch`, diff it against `base_branch`, and return changed files."""
    url = validate_repo_url(repo_url)
    branch = validate_ref(branch, "branch")
    default_branch = await remote_head_branch(url)
    base = (base_branch or "").strip() or default_branch or "main"
    base = validate_ref(base, "base branch")

    if base == branch:
        raise SourceError(
            f"Base branch and target branch are the same ({base!r}). Pick a different base to diff against."
        )

    tmp = tempfile.mkdtemp(prefix="prism-git-")
    try:
        await _run_git(
            ["clone", "--depth", "1", "--single-branch", "--branch", branch, "--", url, tmp],
            timeout=GIT_TIMEOUT,
        )
        try:
            await _run_git(
                ["fetch", "--depth", "1", "origin", f"{base}:refs/remotes/origin/{base}"],
                cwd=tmp,
                timeout=GIT_TIMEOUT,
            )
        except SourceError as e:
            raise SourceError(
                f"Could not fetch base branch {base!r}: {e}. Check that it exists in the repository."
            ) from e

        diff_output = await _run_git(["diff", "--no-color", f"origin/{base}", "HEAD"], cwd=tmp)
        name_status = await _run_git(
            ["diff", "--name-status", f"origin/{base}", "HEAD"], cwd=tmp
        )

        diffs = parse_unified_diff(diff_output)
        status_by_path = _parse_name_status(name_status)
        for entry in diffs:
            entry.status = status_by_path.get(entry.path, entry.status)

        changed_paths = [d.path for d in diffs]
        kept_paths = []
        skipped: List[Tuple[str, str]] = []
        for path in changed_paths:
            reason = skip_reason_for(path)
            if reason is None:
                kept_paths.append(path)
            else:
                skipped.append((path, reason))

        entries: List[Tuple[str, bytes]] = []
        deleted: List[SourceFile] = []
        for rel in kept_paths:
            full = Path(tmp) / rel
            if full.is_file():
                try:
                    entries.append((rel, full.read_bytes()))
                except OSError:
                    continue
            elif status_by_path.get(rel) == "deleted" and len(deleted) < settings.review_max_files:
                # Deleted files have no working-tree content, but their diff is
                # still reviewable — keep them with empty content.
                deleted.append(
                    SourceFile(path=rel, content="", language=language_for_path(rel), size=0)
                )

        outcome = ingest_entries(entries)
        skipped.extend(outcome.skipped)
        files = {f.path: f for f in outcome.files}
        for source in deleted:
            files.setdefault(source.path, source)

        kept_diffs = [d for d in diffs if d.path in files]
        kept_paths = [d.path for d in kept_diffs]

        if not kept_diffs:
            raise SourceError(
                f"No reviewable changes found between {base!r} and {branch!r} "
                "(changed files were empty, binary, or excluded by filters)."
            )

        return BranchSource(
            files=[files[p] for p in kept_paths],
            diffs=kept_diffs,
            branch=branch,
            base_branch=base,
            default_branch=default_branch,
            skipped=skipped,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _parse_name_status(output: str) -> Dict[str, str]:
    status_map: Dict[str, str] = {}
    codes = {"A": "added", "D": "deleted", "M": "modified", "R": "renamed", "C": "copied", "T": "typechange"}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        code = parts[0][0]
        status = codes.get(code, "modified")
        path = parts[-1]
        status_map[path] = status
    return status_map


def diff_to_text(entry: FileDiff) -> str:
    """Render a structured FileDiff back into unified-diff text for the LLM prompt."""
    lines = [
        f"--- a/{entry.old_path or entry.path}",
        f"+++ b/{entry.path}",
    ]
    for hunk in entry.hunks:
        header = f" {hunk.header}" if hunk.header else ""
        lines.append(
            f"@@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@{header}"
        )
        for line in hunk.lines:
            prefix = {"add": "+", "del": "-"}.get(line.type, " ")
            lines.append(prefix + line.text)
    return "\n".join(lines)


def parse_unified_diff(output: str) -> List[FileDiff]:
    """Parse `git diff` output into structured per-file hunks."""
    results: List[FileDiff] = []
    current: Optional[FileDiff] = None
    current_hunk: Optional[DiffHunk] = None
    old_no = new_no = 0
    old_path = new_path = None

    def flush_hunk():
        nonlocal current_hunk
        if current is not None and current_hunk is not None:
            current.hunks.append(current_hunk)
        current_hunk = None

    for raw_line in output.splitlines():
        git_match = _DIFF_GIT_RE.match(raw_line)
        if git_match:
            flush_hunk()
            old_path = git_match.group(1)
            new_path = git_match.group(2)
            current = FileDiff(path=new_path, old_path=old_path if old_path != new_path else None)
            results.append(current)
            continue

        if raw_line.startswith("--- "):
            value = raw_line[4:].strip()
            old_path = None if value == "/dev/null" else value[2:] if value.startswith("a/") else value
            continue
        if raw_line.startswith("+++ "):
            value = raw_line[4:].strip()
            new_path = None if value == "/dev/null" else value[2:] if value.startswith("b/") else value
            if current is not None and new_path:
                current.path = new_path
            continue

        hunk_match = _HUNK_RE.match(raw_line)
        if hunk_match:
            flush_hunk()
            old_no = int(hunk_match.group(1))
            new_no = int(hunk_match.group(3))
            header = (hunk_match.group(5) or "").strip() or None
            if current is None:
                current = FileDiff(path=new_path or old_path or "unknown")
                results.append(current)
            current_hunk = DiffHunk(
                old_start=old_no,
                old_lines=int(hunk_match.group(2) or 1),
                new_start=new_no,
                new_lines=int(hunk_match.group(4) or 1),
                header=header,
            )
            continue

        if current_hunk is None:
            continue

        if raw_line.startswith("+"):
            current_hunk.lines.append(DiffLine(type="add", new_no=new_no, text=raw_line[1:]))
            new_no += 1
        elif raw_line.startswith("-"):
            current_hunk.lines.append(DiffLine(type="del", old_no=old_no, text=raw_line[1:]))
            old_no += 1
        elif raw_line.startswith("\\"):
            continue
        else:
            text = raw_line[1:] if raw_line.startswith(" ") else raw_line
            current_hunk.lines.append(
                DiffLine(type="context", old_no=old_no, new_no=new_no, text=text)
            )
            old_no += 1
            new_no += 1

    flush_hunk()

    for entry in results:
        if entry.old_path and entry.path == entry.old_path:
            entry.old_path = None
    return [e for e in results if e.hunks]
