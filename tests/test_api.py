"""REST API 测试。"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.database import get_connection, init_db, insert_article, insert_daily_report, insert_source
from src.output.api import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("AI_DAILY_DB", str(db_path))
    get_settings.cache_clear()
    monkeypatch.setattr("src.output.api.get_settings", get_settings)
    monkeypatch.setattr("src.database.get_settings", get_settings)
    cfg = get_settings()
    init_db(cfg)
    with get_connection(cfg) as conn:
        insert_source(
            conn,
            {
                "id": "openai-blog",
                "name": "OpenAI Blog",
                "url": "https://openai.com/blog",
                "type": "rss",
                "tier": 1,
                "language": "en",
                "enabled": 1,
                "last_fetched_at": None,
                "error_count": 0,
            },
        )
        insert_article(
            conn,
            {
                "id": "a1",
                "title": "GPT-5 Preview 发布",
                "title_cn": "GPT-5 Preview 发布",
                "url": "https://example.com/a1",
                "source_id": "openai-blog",
                "source_name": "OpenAI Blog",
                "summary": "数学推理能力提升 40%",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "category": "ai-models",
                "score": 92,
                "quality_level": "high",
                "language": "en",
                "merged_from": "[]",
                "content_hash": None,
                "is_selected": 1,
            },
        )
        insert_daily_report(
            conn,
            {
                "date": "2026-07-26",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "file_path": "/tmp/report.md",
                "snr": 0.32,
                "raw_count": 200,
                "l1_count": 60,
                "l2_count": 20,
                "stats": "{}",
            },
        )

    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_items_selected_mode(client) -> None:
    response = client.get("/api/v1/items", params={"mode": "selected", "limit": 10})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["title"]


def test_latest_daily(client) -> None:
    response = client.get("/api/v1/dailies/latest")
    assert response.status_code == 200
    assert response.json()["date"] == "2026-07-26"


def test_sources_endpoint(client) -> None:
    response = client.get("/api/v1/sources")
    assert response.status_code == 200
    assert "sources" in response.json()


def test_snr_endpoint(client) -> None:
    response = client.get("/api/v1/stats/snr")
    assert response.status_code == 200
    assert "trend" in response.json()


def test_dashboard_endpoint(client) -> None:
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "AI 知识侦察兵" in response.text
    assert "TOP 3" in response.text


def test_dashboard_empty_state(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "empty.db"
    monkeypatch.setenv("AI_DAILY_DB", str(db_path))
    get_settings.cache_clear()
    monkeypatch.setattr("src.output.api.get_settings", get_settings)
    monkeypatch.setattr("src.database.get_settings", get_settings)

    cfg = get_settings()
    init_db(cfg)
    with TestClient(app) as empty_client:
        response = empty_client.get("/dashboard")
        assert response.status_code == 200
        assert "暂无日报" in response.text


def test_root_redirects_to_dashboard(client) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code in {307, 302, 303}
    assert response.headers["location"] == "/dashboard"
