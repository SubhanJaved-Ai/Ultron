"""Unit and regression tests for LLM client portability and key resolution."""

from __future__ import annotations

from pathlib import Path

from openjarvis.server.llm_client import (
    UltronBrain,
    _read_key_from_file,
    _resolve_api_key,
)


class TestLLMClientPortability:
    """Validate environment variable resolution and path portability."""

    def test_process_env_highest_precedence(self, monkeypatch, tmp_path: Path) -> None:
        """Process env var must override any file-based keys."""
        file_env = tmp_path / ".env"
        file_env.write_text("GEMINI_API_KEY=file-key\n", encoding="utf-8")

        monkeypatch.setenv("GEMINI_API_KEY", "proc-gemini-key")
        assert _resolve_api_key(env_path=file_env) == "proc-gemini-key"

    def test_google_api_key_fallback(self, monkeypatch, tmp_path: Path) -> None:
        """GOOGLE_API_KEY is honored if GEMINI_API_KEY is not set."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "proc-google-key")
        assert _resolve_api_key() == "proc-google-key"

    def test_resolve_from_explicit_file(self, monkeypatch, tmp_path: Path) -> None:
        """Explicit env path is parsed correctly when process env is unset."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        file_env = tmp_path / ".env"
        file_env.write_text("GEMINI_API_KEY=explicit-key\n", encoding="utf-8")
        assert _resolve_api_key(env_path=file_env) == "explicit-key"

    def test_resolve_from_source_root(self, monkeypatch, tmp_path: Path) -> None:
        """Dynamic source checkout root .env is resolved when process env is unset."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("OPENJARVIS_WORKSPACE", raising=False)

        mock_root = tmp_path / "repo"
        mock_root.mkdir()
        (mock_root / ".env").write_text("GEMINI_API_KEY=repo-root-key\n", encoding="utf-8")

        monkeypatch.setattr(
            "openjarvis.server.llm_client._find_source_root",
            lambda: mock_root,
        )
        assert _resolve_api_key() == "repo-root-key"

    def test_resolve_from_workspace_env(self, monkeypatch, tmp_path: Path) -> None:
        """OPENJARVIS_WORKSPACE .env is resolved if configured."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        ws_dir = tmp_path / "workspace"
        ws_dir.mkdir()
        (ws_dir / ".env").write_text("GOOGLE_API_KEY=workspace-key\n", encoding="utf-8")

        monkeypatch.setenv("OPENJARVIS_WORKSPACE", str(ws_dir))
        # Ensure source root doesn't intercept
        monkeypatch.setattr(
            "openjarvis.server.llm_client._find_source_root",
            lambda: None,
        )
        assert _resolve_api_key() == "workspace-key"

    def test_resolve_from_cloud_keys_env(self, monkeypatch, tmp_path: Path) -> None:
        """User config directory cloud-keys.env is resolved as fallback."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("OPENJARVIS_WORKSPACE", raising=False)

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "cloud-keys.env").write_text(
            "GEMINI_API_KEY=cloud-config-key\n", encoding="utf-8"
        )

        monkeypatch.setattr(
            "openjarvis.server.llm_client._find_source_root",
            lambda: None,
        )
        monkeypatch.setattr(
            "openjarvis.server.llm_client.get_config_dir",
            lambda: config_dir,
        )
        assert _resolve_api_key() == "cloud-config-key"

    def test_missing_env_safe(self, monkeypatch, tmp_path: Path) -> None:
        """Absence of .env or config files returns empty string without crashing."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("OPENJARVIS_WORKSPACE", raising=False)

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        monkeypatch.setattr(
            "openjarvis.server.llm_client._find_source_root",
            lambda: None,
        )
        monkeypatch.setattr(
            "openjarvis.server.llm_client.get_config_dir",
            lambda: empty_dir,
        )
        assert _resolve_api_key() == ""

    def test_read_key_handles_quotes_and_comments(self, tmp_path: Path) -> None:
        """Quotes, spaces, and comments are parsed cleanly."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# Comment line\n"
            "OTHER_VAR=xyz\n"
            "GEMINI_API_KEY=\"quoted-secret-123\"\n",
            encoding="utf-8",
        )
        assert _read_key_from_file(env_file) == "quoted-secret-123"

        # Single quotes
        env_file.write_text("GOOGLE_API_KEY='single-quoted-456'\n", encoding="utf-8")
        assert _read_key_from_file(env_file) == "single-quoted-456"

    def test_no_hardcoded_paths_in_source(self) -> None:
        """Verify source code contains no developer-specific paths."""
        source_file = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "openjarvis"
            / "server"
            / "llm_client.py"
        )
        content = source_file.read_text(encoding="utf-8").lower()
        assert "jarvis 2.0" not in content
        assert "d:/" not in content
        assert "d:\\" not in content

    def test_ultron_brain_fallback_without_key(self, monkeypatch, tmp_path: Path) -> None:
        """UltronBrain cleanly executes local reasoning when no key is present."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        brain = UltronBrain(api_key="")
        resp = brain.generate_response("Who are you?")
        assert "ultron" in resp.lower()
