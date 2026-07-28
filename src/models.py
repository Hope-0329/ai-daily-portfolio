"""Pydantic 数据模型定义。"""

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Category(str, Enum):
    """文章分类。"""

    AI_MODELS = "ai-models"
    AI_PRODUCTS = "ai-products"
    INDUSTRY = "industry"
    PAPER = "paper"
    TIP = "tip"


class SourceType(str, Enum):
    """信源接入类型。"""

    RSS = "rss"
    API = "api"
    WEB = "web"
    RSSHUB = "rsshub"


class QualityLevel(str, Enum):
    """内容质量等级。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Source(BaseModel):
    """信源注册信息。"""

    id: str
    name: str
    name_display: str
    url: str
    type: SourceType
    tier: int = Field(ge=1, le=3, description="1=核心, 2=辅助, 3=备用")
    language: str = Field(description="zh 或 en")
    category_weights: dict[str, float] = Field(default_factory=dict)
    enabled: bool = True
    fetch_interval_min: int = 60
    fetch_timeout: int | None = Field(default=None, description="单源超时秒数，覆盖全局配置")
    disable_reason: str | None = Field(default=None, description="禁用原因说明")
    api_headers: dict[str, str] = Field(default_factory=dict, description="API 信源自定义请求头")


class Article(BaseModel):
    """采集到的单篇文章。"""

    id: str = Field(description="URL 哈希")
    title: str
    title_cn: str | None = None
    url: str
    source_id: str
    source_name: str
    summary: str | None = Field(default=None, description="LLM 生成的摘要")
    summary_raw: str | None = Field(default=None, description="原文摘要")
    summary_cn: str | None = Field(default=None, description="摘要中文翻译")
    content: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    category: Category | None = None
    score: float = Field(default=0.0, ge=0, le=100)
    quality_level: QualityLevel | None = None
    language: str | None = None
    merged_from: list[str] = Field(default_factory=list)
    pre_summarized: bool = Field(default=False, description="预摘要源（如 AIHOT），跳过 LLM 摘要")
    pre_classified: bool = Field(default=False, description="预分类源，跳过 LLM 分类")


class DailyReport(BaseModel):
    """生成的日报结构。"""

    date: date
    generated_at: datetime
    sections: dict[str, Any] = Field(default_factory=dict)
    top_stories: list[Article] = Field(default_factory=list)
    topic_pool: list[str] = Field(default_factory=list)
    thoughts: str = ""
    snr: float = 0.0
    stats: dict[str, Any] = Field(default_factory=dict)
