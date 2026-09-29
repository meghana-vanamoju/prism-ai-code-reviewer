import importlib
import subprocess
from pathlib import Path

import pytest

from app import config as config_module
from app.config import BACKEND_DIR, REPO_ROOT, Settings, env_files

DOCUMENTED_VARS = [
    "HINDSIGHT_BASE_URL",
    "HINDSIGHT_BANK_ID",
    "HINDSIGHT_RETAIN_EXTRACTION_MODE",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "API_HOST",
    "API_PORT",
    "CORS_ORIGINS",
]


def parse_env_file(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


@pytest.fixture
def clean_env(monkeypatch):
    for name in DOCUMENTED_VARS:
        monkeypatch.delenv(name, raising=False)


class TestEnvFileResolution:
    def test_resolves_repository_root_env(self):
        assert REPO_ROOT == BACKEND_DIR.parent
        assert env_files()[0] == REPO_ROOT / ".env"

    def test_env_path_is_absolute(self):
        assert env_files()[0].is_absolute()

    def test_repo_root_is_the_real_repository_root(self):
        """The resolved root must be the actual repo root, not a guess."""
        assert (REPO_ROOT / ".env.example").is_file()
        assert (REPO_ROOT / "backend" / "app" / "config.py").is_file()

    def test_env_keeps_its_place_at_repository_root(self):
        assert (REPO_ROOT / ".env").is_file()
        assert (REPO_ROOT / ".env.example").is_file()

    def test_optional_backend_override_is_loaded_last(self):
        assert env_files()[-1] == BACKEND_DIR / ".env"

    def test_resolution_does_not_depend_on_working_directory(self, tmp_path, monkeypatch):
        before = env_files()
        with monkeypatch.context() as scoped:
            scoped.chdir(tmp_path)
            reloaded = importlib.reload(config_module)
            during = reloaded.env_files()
        importlib.reload(config_module)
        assert during == before

    def test_resolution_does_not_depend_on_working_directory_from_backend(self, monkeypatch):
        before = env_files()
        with monkeypatch.context() as scoped:
            scoped.chdir(BACKEND_DIR)
            reloaded = importlib.reload(config_module)
            during = reloaded.env_files()
        importlib.reload(config_module)
        assert during == before

    def test_env_is_not_tracked_by_git(self):
        """Secrets must never be committed."""
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".env"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, "root .env is tracked by git"

    def test_env_is_git_ignored(self):
        result = subprocess.run(
            ["git", "check-ignore", ".env"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "root .env is not git-ignored"


class TestSettingsLoading:
    def test_documented_variables_cover_every_example_entry(self):
        example_keys = set(parse_env_file(REPO_ROOT / ".env.example"))
        assert set(DOCUMENTED_VARS) <= example_keys

    def test_example_keys_map_onto_settings_fields(self):
        fields = set(Settings.model_fields)
        for name in DOCUMENTED_VARS:
            assert name.lower() in fields, f"{name} is not a Settings field"

    def test_settings_reads_documented_location(self, clean_env):
        """Settings must populate from the repository-root .env."""
        settings = Settings(_env_file=env_files())
        on_disk = parse_env_file(REPO_ROOT / ".env")
        assert settings.hindsight_base_url == on_disk["HINDSIGHT_BASE_URL"]
        assert settings.hindsight_bank_id == on_disk["HINDSIGHT_BANK_ID"]
        assert settings.groq_model == on_disk["GROQ_MODEL"]
        assert settings.cors_origins == on_disk["CORS_ORIGINS"]

    def test_settings_maps_each_documented_variable(self, tmp_path, clean_env):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "HINDSIGHT_BASE_URL=http://hindsight.internal:9999\n"
            "HINDSIGHT_BANK_ID=team-alpha\n"
            "HINDSIGHT_RETAIN_EXTRACTION_MODE=chunks\n"
            "GROQ_API_KEY=test-key-value\n"
            "GROQ_MODEL=test-model\n"
            "API_HOST=127.0.0.1\n"
            "API_PORT=9001\n"
            "CORS_ORIGINS=http://localhost:5173, http://localhost:3000\n",
            encoding="utf-8",
        )

        settings = Settings(_env_file=env_file)

        assert settings.hindsight_base_url == "http://hindsight.internal:9999"
        assert settings.hindsight_bank_id == "team-alpha"
        assert settings.hindsight_retain_extraction_mode == "chunks"
        assert settings.groq_api_key == "test-key-value"
        assert settings.groq_model == "test-model"
        assert settings.api_host == "127.0.0.1"
        assert settings.api_port == 9001
        assert settings.cors_origins_list == [
            "http://localhost:5173",
            "http://localhost:3000",
        ]

    def test_later_file_overrides_earlier(self, tmp_path, clean_env):
        """A local backend/.env must win over the shared root .env."""
        low = tmp_path / "root.env"
        low.write_text("GROQ_MODEL=from-root\nHINDSIGHT_BANK_ID=from-root\n", encoding="utf-8")
        high = tmp_path / "backend.env"
        high.write_text("GROQ_MODEL=from-backend\n", encoding="utf-8")

        settings = Settings(_env_file=(low, high))

        assert settings.groq_model == "from-backend"
        assert settings.hindsight_bank_id == "from-root"

    def test_value_with_surrounding_whitespace_is_stripped(self, tmp_path, clean_env):
        env_file = tmp_path / ".env"
        env_file.write_text("GROQ_API_KEY=  spaced-key  \n", encoding="utf-8")

        settings = Settings(_env_file=env_file)

        assert settings.groq_api_key == "spaced-key"

    def test_no_secret_is_hardcoded_in_settings_defaults(self):
        for name, field in Settings.model_fields.items():
            if "key" in name or "secret" in name or "token" in name:
                assert field.default in ("", None), f"{name} must default to empty"
