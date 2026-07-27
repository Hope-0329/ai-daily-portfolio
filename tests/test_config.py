"""配置模块单元测试。"""

from src.config import Settings, ensure_api_key, get_settings, settings


def test_default_fetch_timeout() -> None:
    cfg = Settings()
    assert cfg.fetch_timeout == 25


def test_default_fetch_retry_settings() -> None:
    cfg = Settings()
    assert cfg.fetch_retry_count == 3
    assert cfg.fetch_retry_delay == 3


def test_default_max_concurrent() -> None:
    cfg = Settings()
    assert cfg.max_concurrent == 6


def test_default_l1_min_score() -> None:
    cfg = Settings()
    assert cfg.l1_min_score == 60


def test_default_l2_top_n() -> None:
    cfg = Settings()
    assert cfg.l2_top_n == 25


def test_default_deepseek_base_url() -> None:
    cfg = Settings()
    assert cfg.deepseek_base_url == "https://api.deepseek.com/v1"


def test_default_paths_are_configurable() -> None:
    cfg = Settings()
    assert cfg.db_path.name == "ai_daily.db"
    assert "data" in cfg.db_path.parts
    assert cfg.sources_config.name == "sources.yaml"
    assert "data" in cfg.sources_config.parts


def test_ai_daily_db_env_override(monkeypatch, tmp_path) -> None:
    custom = tmp_path / "cloud.db"
    monkeypatch.setenv("AI_DAILY_DB", str(custom))
    get_settings.cache_clear()
    try:
        cfg = Settings()
        assert cfg.db_path == custom
    finally:
        get_settings.cache_clear()


def test_obsidian_enabled_parses_false_string(monkeypatch) -> None:
    monkeypatch.setenv("OBSIDIAN_ENABLED", "false")
    get_settings.cache_clear()
    try:
        cfg = Settings()
        assert cfg.obsidian_enabled is False
    finally:
        get_settings.cache_clear()


def test_get_settings_returns_settings_instance() -> None:
    assert isinstance(get_settings(), Settings)


def test_module_settings_has_api_key() -> None:
    assert settings.deepseek_api_key.startswith("sk-")


def test_ensure_api_key_raises_when_missing(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    cfg = Settings()
    try:
        ensure_api_key(cfg)
        assert False, "应抛出 ValueError"
    except ValueError as exc:
        assert "DEEPSEEK_API_KEY" in str(exc)
    finally:
        get_settings.cache_clear()
