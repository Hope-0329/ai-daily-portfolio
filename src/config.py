"""应用配置：从环境变量与 .env 文件加载。"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（src 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """全局配置项，所有路径均可通过环境变量覆盖。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-v4-flash", alias="DEEPSEEK_MODEL")
    obsidian_root: str = "D:\\肠肠的Obsidian\\肠肠的obsidian\\30-项目\\AI博主与日报\\"
    obsidian_enabled: bool = Field(default=True, alias="OBSIDIAN_ENABLED")
    db_path: Path = Field(
        default=PROJECT_ROOT / "data" / "ai_daily.db",
        alias="AI_DAILY_DB",
    )
    sources_config: Path = PROJECT_ROOT / "data" / "sources.yaml"
    fetch_timeout: int = 25
    fetch_retry_count: int = 3
    fetch_retry_delay: int = 3
    max_concurrent: int = 6
    l1_min_score: int = 60
    l2_top_n: int = 25
    l2_candidate_limit: int = 30
    l2_max_per_source: int = 5
    l2_max_papers: int = 8
    arxiv_max_items: int = 15
    pipeline_concurrency: int = 5
    scheduler_enabled: bool = Field(default=True, alias="ENABLE_SCHEDULER")
    deep_analysis_max_count: int = 3
    deep_analysis_min_score_high: int = 80
    deep_analysis_min_score_fallback: int = 70
    deep_analysis_content_limit: int = 6000
    schedule_hour: int = 7
    schedule_minute: int = 0
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    index_filename: str = "INDEX.md"
    log_level: str = "INFO"

    @field_validator("deepseek_api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        """API Key 为空时允许加载配置，实际调用 LLM 前再校验。"""
        return value.strip()

    @field_validator("obsidian_enabled", "scheduler_enabled", mode="before")
    @classmethod
    def parse_bool_env(cls, value: object) -> bool:
        """解析环境变量中的布尔字符串。"""
        if isinstance(value, bool):
            return value
        if value is None:
            return True
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @field_validator("db_path", mode="before")
    @classmethod
    def normalize_db_path(cls, value: object) -> Path:
        """支持字符串形式的数据库路径环境变量。"""
        if isinstance(value, Path):
            return value
        return Path(str(value))


@lru_cache
def get_settings() -> Settings:
    """获取配置单例（优先 .env，其次系统环境变量）。"""
    return Settings()


def ensure_api_key(settings: Settings | None = None) -> str:
    """在调用 LLM 前校验 API Key 是否已配置。"""
    cfg = settings or get_settings()
    if not cfg.deepseek_api_key.startswith("sk-"):
        raise ValueError(
            "DEEPSEEK_API_KEY 未配置。请在项目根目录 .env 文件中设置，或写入系统环境变量。"
        )
    return cfg.deepseek_api_key


# 便捷访问入口（与 get_settings 等价）
settings = get_settings()
