"""本机配置接口与 .env 写入测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import config as config_router  # noqa: E402


def test_write_env_preserves_comments_and_updates_keys(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# keep this comment\nDEEPSEEK_API_KEY=old\nHOST=127.0.0.1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_router, "ENV_FILE", env_file)

    config_router._write_env({"DEEPSEEK_API_KEY": "new", "DEFAULT_PROVIDER": "ollama"})

    text = env_file.read_text(encoding="utf-8")
    assert "# keep this comment" in text
    assert "DEEPSEEK_API_KEY=new" in text
    assert "HOST=127.0.0.1" in text
    assert "DEFAULT_PROVIDER=ollama" in text
    assert "old" not in text


def test_mask_never_returns_full_key() -> None:
    assert config_router._mask("sk-1234567890") == "sk-1••••7890"
    assert config_router._mask("") == ""
