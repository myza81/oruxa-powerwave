"""Coverage for the frontend container entrypoint.

The script lives under frontend/, but this is the repository's only test
harness, so it runs here. It is executed with a real ``sh`` and a controlled
environment; ``POWERWAVE_CONFIG_DIR`` redirects its output into tmp_path.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "docker-entrypoint.d"
    / "10-powerwave-config.sh"
)

FALLBACK_URL = "http://127.0.0.1:8000"
PROD_URL = "https://api.powerwave.example"

pytestmark = pytest.mark.skipif(
    shutil.which("sh") is None, reason="requires a POSIX sh"
)


def run(config_dir: Path, **env: str) -> subprocess.CompletedProcess:
    """Run the entrypoint with only the variables a container would supply."""
    base = {"PATH": os.environ.get("PATH", "")}
    if "SYSTEMROOT" in os.environ:  # sh.exe needs this on Windows
        base["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    base["POWERWAVE_CONFIG_DIR"] = config_dir.as_posix()

    return subprocess.run(
        ["sh", SCRIPT.as_posix()],
        env={**base, **env},
        capture_output=True,
        text=True,
    )


def config_js(config_dir: Path) -> str:
    return (config_dir / "config.js").read_text(encoding="utf-8")


def test_script_exists_and_is_the_one_the_dockerfile_copies():
    assert SCRIPT.is_file()
    dockerfile = (SCRIPT.parents[2] / "frontend" / "Dockerfile").read_text()
    assert "docker-entrypoint.d/10-powerwave-config.sh" in dockerfile


class TestDevelopmentFallback:
    def test_no_environment_and_no_url_uses_fallback(self, tmp_path):
        result = run(tmp_path)

        assert result.returncode == 0, result.stderr
        assert FALLBACK_URL in config_js(tmp_path)

    def test_development_without_url_uses_fallback(self, tmp_path):
        result = run(tmp_path, ENVIRONMENT="development")

        assert result.returncode == 0, result.stderr
        assert FALLBACK_URL in config_js(tmp_path)

    def test_development_respects_an_explicit_url(self, tmp_path):
        result = run(
            tmp_path, ENVIRONMENT="development", API_BASE_URL="http://localhost:9999"
        )

        assert result.returncode == 0, result.stderr
        assert "http://localhost:9999" in config_js(tmp_path)
        assert FALLBACK_URL not in config_js(tmp_path)


class TestProductionFailsFast:
    @pytest.mark.parametrize(
        "env",
        [
            pytest.param({}, id="unset"),
            pytest.param({"API_BASE_URL": ""}, id="empty"),
            pytest.param({"API_BASE_URL": "   "}, id="whitespace"),
            pytest.param({"API_BASE_URL": "\t"}, id="tab"),
        ],
    )
    def test_production_without_a_usable_url_fails(self, tmp_path, env):
        result = run(tmp_path, ENVIRONMENT="production", **env)

        assert result.returncode != 0
        assert "API_BASE_URL" in result.stderr

    def test_failure_does_not_write_a_config_file(self, tmp_path):
        run(tmp_path, ENVIRONMENT="production")

        assert not (tmp_path / "config.js").exists()

    def test_failure_does_not_leak_a_localhost_url(self, tmp_path):
        result = run(tmp_path, ENVIRONMENT="production")

        assert FALLBACK_URL not in result.stdout
        assert FALLBACK_URL not in result.stderr


class TestProductionSucceedsWhenConfigured:
    def test_production_with_url_writes_that_url(self, tmp_path):
        result = run(tmp_path, ENVIRONMENT="production", API_BASE_URL=PROD_URL)

        assert result.returncode == 0, result.stderr
        assert PROD_URL in config_js(tmp_path)
        assert FALLBACK_URL not in config_js(tmp_path)

    def test_written_config_defines_the_expected_global(self, tmp_path):
        run(tmp_path, ENVIRONMENT="production", API_BASE_URL=PROD_URL)

        content = config_js(tmp_path)
        assert "window.POWERWAVE_CONFIG" in content
        assert "apiBaseUrl" in content

    def test_no_production_hostname_is_baked_into_the_script(self):
        """The script must stay configuration-driven."""
        source = SCRIPT.read_text(encoding="utf-8")

        assert "oruxa.uk" not in source
        assert "https://" not in source
