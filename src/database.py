"""SQLite 数据库初始化与基础 CRUD。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

from src.config import Settings, get_settings
from src.models import Article, Source


def _ensure_parent_dir(db_path: Path) -> None:
    """确保数据库文件所在目录存在。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _connect(db_path: Path) -> sqlite3.Connection:
    """创建 SQLite 连接并启用外键约束。"""
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection(settings: Settings | None = None) -> Iterator[sqlite3.Connection]:
    """获取数据库连接上下文管理器。"""
    cfg = settings or get_settings()
    conn = _connect(Path(cfg.db_path))
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(settings: Settings | None = None) -> None:
    """初始化数据库表结构。"""
    cfg = settings or get_settings()
    with get_connection(cfg) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                type TEXT NOT NULL,
                tier INTEGER NOT NULL,
                language TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_fetched_at TEXT,
                error_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                title_cn TEXT,
                url TEXT NOT NULL UNIQUE,
                source_id TEXT NOT NULL,
                source_name TEXT NOT NULL,
                summary TEXT,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                category TEXT,
                score REAL NOT NULL DEFAULT 0,
                quality_level TEXT,
                language TEXT,
                merged_from TEXT,
                content_hash TEXT,
                is_selected INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );

            CREATE TABLE IF NOT EXISTS daily_reports (
                date TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                file_path TEXT,
                snr REAL NOT NULL DEFAULT 0,
                raw_count INTEGER NOT NULL DEFAULT 0,
                l1_count INTEGER NOT NULL DEFAULT 0,
                l2_count INTEGER NOT NULL DEFAULT 0,
                stats TEXT
            );

            CREATE TABLE IF NOT EXISTS source_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL,
                articles_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                response_time_ms INTEGER,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );

            CREATE INDEX IF NOT EXISTS idx_articles_fetched_at ON articles(fetched_at);
            CREATE INDEX IF NOT EXISTS idx_articles_source_id ON articles(source_id);
            CREATE INDEX IF NOT EXISTS idx_source_health_source_date
                ON source_health(source_id, date);
            """
        )


# ── 信源 CRUD ──────────────────────────────────────────────


def insert_source(conn: sqlite3.Connection, source: dict[str, Any]) -> None:
    """插入或更新信源（底层字典接口）。"""
    conn.execute(
        """
        INSERT INTO sources (id, name, url, type, tier, language, enabled, last_fetched_at, error_count)
        VALUES (:id, :name, :url, :type, :tier, :language, :enabled, :last_fetched_at, :error_count)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            url = excluded.url,
            type = excluded.type,
            tier = excluded.tier,
            language = excluded.language,
            enabled = excluded.enabled,
            last_fetched_at = excluded.last_fetched_at,
            error_count = excluded.error_count
        """,
        {
            "enabled": 1 if source.get("enabled", True) else 0,
            **{k: source.get(k) for k in (
                "id", "name", "url", "type", "tier", "language",
                "last_fetched_at", "error_count",
            )},
        },
    )


def get_source(conn: sqlite3.Connection, source_id: str) -> dict[str, Any] | None:
    """按 ID 查询信源。"""
    row = conn.execute(
        "SELECT * FROM sources WHERE id = ?",
        (source_id,),
    ).fetchone()
    return dict(row) if row else None


def list_sources(conn: sqlite3.Connection, enabled_only: bool = False) -> list[dict[str, Any]]:
    """列出所有信源。"""
    sql = "SELECT * FROM sources"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY tier ASC, name ASC"
    return [dict(row) for row in conn.execute(sql).fetchall()]


def upsert_source(
    conn: sqlite3.Connection,
    source: Source,
    *,
    last_fetched_at: str | None = None,
    increment_error: bool = False,
) -> None:
    """插入或更新信源模型。"""
    existing = get_source(conn, source.id)
    error_count = int(existing.get("error_count", 0)) if existing else 0
    if increment_error:
        error_count += 1
    fetched_at = last_fetched_at
    if fetched_at is None and existing:
        fetched_at = existing.get("last_fetched_at")
    insert_source(
        conn,
        {
            "id": source.id,
            "name": source.name,
            "url": source.url,
            "type": source.type.value,
            "tier": source.tier,
            "language": source.language,
            "enabled": source.enabled,
            "last_fetched_at": fetched_at,
            "error_count": error_count,
        },
    )


# ── 文章 CRUD ──────────────────────────────────────────────


def insert_article(conn: sqlite3.Connection, article: dict[str, Any]) -> None:
    """插入或更新文章。"""
    merged_from = article.get("merged_from")
    if isinstance(merged_from, list):
        merged_from = json.dumps(merged_from, ensure_ascii=False)

    conn.execute(
        """
        INSERT INTO articles (
            id, title, title_cn, url, source_id, source_name, summary,
            published_at, fetched_at, category, score, quality_level,
            language, merged_from, content_hash, is_selected
        ) VALUES (
            :id, :title, :title_cn, :url, :source_id, :source_name, :summary,
            :published_at, :fetched_at, :category, :score, :quality_level,
            :language, :merged_from, :content_hash, :is_selected
        )
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            title_cn = excluded.title_cn,
            summary = excluded.summary,
            score = excluded.score,
            quality_level = excluded.quality_level,
            is_selected = excluded.is_selected,
            category = excluded.category
        """,
        {
            "is_selected": 1 if article.get("is_selected") else 0,
            **{k: article.get(k) for k in (
                "id", "title", "title_cn", "url", "source_id", "source_name",
                "summary", "published_at", "fetched_at", "category", "score",
                "quality_level", "language", "merged_from", "content_hash",
            )},
        },
    )


def url_exists_within_hours(
    conn: sqlite3.Connection,
    url: str,
    hours: int = 24,
) -> bool:
    """检查 URL 是否在指定小时数内已入库。"""
    row = conn.execute(
        """
        SELECT 1 FROM articles
        WHERE url = ? AND datetime(fetched_at) > datetime('now', ?)
        """,
        (url, f"-{hours} hours"),
    ).fetchone()
    return row is not None


def _article_to_row(article: Article) -> dict[str, Any]:
    """将 Article 模型转为数据库行。"""
    merged_from = article.merged_from
    if isinstance(merged_from, list):
        merged_from = json.dumps(merged_from, ensure_ascii=False)
    return {
        "id": article.id,
        "title": article.title,
        "title_cn": article.title_cn,
        "url": article.url,
        "source_id": article.source_id,
        "source_name": article.source_name,
        "summary": article.summary_raw or article.summary,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "fetched_at": article.fetched_at.isoformat(),
        "category": article.category.value if article.category else None,
        "score": article.score,
        "quality_level": article.quality_level.value if article.quality_level else None,
        "language": article.language,
        "merged_from": merged_from,
        "content_hash": None,
        "is_selected": 0,
    }


def insert_articles(
    conn: sqlite3.Connection,
    articles: list[Article],
    *,
    skip_recent_hours: int = 24,
) -> int:
    """批量插入文章，跳过重复 URL 及近期已入库 URL。"""
    inserted = 0
    for article in articles:
        if url_exists_within_hours(conn, article.url, skip_recent_hours):
            continue
        row = _article_to_row(article)
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO articles (
                id, title, title_cn, url, source_id, source_name, summary,
                published_at, fetched_at, category, score, quality_level,
                language, merged_from, content_hash, is_selected
            ) VALUES (
                :id, :title, :title_cn, :url, :source_id, :source_name, :summary,
                :published_at, :fetched_at, :category, :score, :quality_level,
                :language, :merged_from, :content_hash, :is_selected
            )
            """,
            row,
        )
        if cursor.rowcount > 0:
            inserted += 1
    return inserted


def get_article(conn: sqlite3.Connection, article_id: str) -> dict[str, Any] | None:
    """按 ID 查询文章。"""
    row = conn.execute(
        "SELECT * FROM articles WHERE id = ?",
        (article_id,),
    ).fetchone()
    return dict(row) if row else None


def get_articles_by_date(
    conn: sqlite3.Connection,
    target_date: date,
    *,
    selected_only: bool = False,
) -> list[dict[str, Any]]:
    """按抓取日期查询文章（基于 fetched_at 的日期部分）。"""
    date_str = target_date.isoformat()
    sql = """
        SELECT * FROM articles
        WHERE date(fetched_at) = ?
    """
    params: list[Any] = [date_str]
    if selected_only:
        sql += " AND is_selected = 1"
    sql += " ORDER BY score DESC"
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


# ── 日报 CRUD ──────────────────────────────────────────────


def insert_daily_report(conn: sqlite3.Connection, report: dict[str, Any]) -> None:
    """插入或更新日报记录。"""
    stats = report.get("stats")
    if isinstance(stats, dict):
        stats = json.dumps(stats, ensure_ascii=False)

    conn.execute(
        """
        INSERT INTO daily_reports (
            date, generated_at, file_path, snr, raw_count, l1_count, l2_count, stats
        ) VALUES (
            :date, :generated_at, :file_path, :snr, :raw_count, :l1_count, :l2_count, :stats
        )
        ON CONFLICT(date) DO UPDATE SET
            generated_at = excluded.generated_at,
            file_path = excluded.file_path,
            snr = excluded.snr,
            raw_count = excluded.raw_count,
            l1_count = excluded.l1_count,
            l2_count = excluded.l2_count,
            stats = excluded.stats
        """,
        {
            "stats": stats,
            **{k: report.get(k) for k in (
                "date", "generated_at", "file_path", "snr",
                "raw_count", "l1_count", "l2_count",
            )},
        },
    )


def get_daily_report(conn: sqlite3.Connection, report_date: date) -> dict[str, Any] | None:
    """按日期查询日报。"""
    row = conn.execute(
        "SELECT * FROM daily_reports WHERE date = ?",
        (report_date.isoformat(),),
    ).fetchone()
    return dict(row) if row else None


# ── 信源健康日志 ───────────────────────────────────────────


def insert_source_health(conn: sqlite3.Connection, health: dict[str, Any]) -> int:
    """写入信源健康日志，返回自增 ID。"""
    cursor = conn.execute(
        """
        INSERT INTO source_health (
            source_id, date, status, articles_count, error_message, response_time_ms
        ) VALUES (
            :source_id, :date, :status, :articles_count, :error_message, :response_time_ms
        )
        """,
        health,
    )
    return cursor.lastrowid or 0


def log_source_health(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    status: str,
    count: int,
    error_msg: str | None = None,
    response_time: int | None = None,
    log_date: date | None = None,
) -> int:
    """记录信源健康日志。"""
    return insert_source_health(
        conn,
        {
            "source_id": source_id,
            "date": (log_date or date.today()).isoformat(),
            "status": status,
            "articles_count": count,
            "error_message": error_msg,
            "response_time_ms": response_time,
        },
    )


def get_source_health_by_date(
    conn: sqlite3.Connection,
    source_id: str,
    target_date: date,
) -> list[dict[str, Any]]:
    """查询某信源在指定日期的健康日志。"""
    rows = conn.execute(
        """
        SELECT * FROM source_health
        WHERE source_id = ? AND date = ?
        ORDER BY id DESC
        """,
        (source_id, target_date.isoformat()),
    ).fetchall()
    return [dict(row) for row in rows]


# ── API 查询 ───────────────────────────────────────────────


WINDOW_SQL = {
    "24h": "-24 hours",
    "7d": "-7 days",
    "30d": "-30 days",
}


def _merged_count(raw: str | None) -> int:
    if not raw:
        return 1
    try:
        payload = json.loads(raw)
        if isinstance(payload, list):
            return len(payload) + 1
    except json.JSONDecodeError:
        pass
    return 1


def row_to_item(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """将数据库行转为 API 响应项。"""
    data = dict(row)
    return {
        "id": data["id"],
        "title": data["title"],
        "title_cn": data.get("title_cn") or data["title"],
        "url": data["url"],
        "source_name": data["source_name"],
        "summary": data.get("summary"),
        "published_at": data.get("published_at"),
        "category": data.get("category"),
        "score": data.get("score", 0),
        "merged_count": _merged_count(data.get("merged_from")),
    }


def query_articles(
    conn: sqlite3.Connection,
    *,
    mode: str = "all",
    window: str = "24h",
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """分页查询文章列表。"""
    window_sql = WINDOW_SQL.get(window, "-24 hours")
    clauses = ["datetime(fetched_at) > datetime('now', ?)"]
    params: list[Any] = [window_sql]

    if mode == "selected":
        clauses.append("is_selected = 1")

    if q:
        clauses.append("(title LIKE ? OR title_cn LIKE ? OR summary LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])

    where = " AND ".join(clauses)
    total = conn.execute(f"SELECT COUNT(*) FROM articles WHERE {where}", params).fetchone()[0]
    offset = max(page - 1, 0) * page_size
    rows = conn.execute(
        f"""
        SELECT * FROM articles
        WHERE {where}
        ORDER BY score DESC, fetched_at DESC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()
    return [row_to_item(row) for row in rows], int(total)


def get_latest_daily_report_row(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """获取最新日报记录。"""
    row = conn.execute(
        "SELECT * FROM daily_reports ORDER BY date DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def get_snr_trend(conn: sqlite3.Connection, *, days: int = 30) -> list[dict[str, Any]]:
    """获取最近 N 天 SNR 趋势。"""
    rows = conn.execute(
        """
        SELECT date, snr, raw_count, l1_count, l2_count, stats
        FROM daily_reports
        WHERE date >= date('now', ?)
        ORDER BY date ASC
        """,
        (f"-{days} days",),
    ).fetchall()
    trend: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        stats = item.get("stats")
        quality_rate = None
        if stats:
            try:
                quality_rate = json.loads(stats).get("quality_rate")
            except json.JSONDecodeError:
                quality_rate = None
        trend.append(
            {
                "date": item["date"],
                "snr": item.get("snr", 0),
                "raw_count": item.get("raw_count", 0),
                "l1_count": item.get("l1_count", 0),
                "l2_count": item.get("l2_count", 0),
                "quality_rate": quality_rate,
            }
        )
    return trend


def get_sources_health_summary(
    conn: sqlite3.Connection,
    *,
    days: int = 7,
) -> list[dict[str, Any]]:
    """获取信源健康摘要（最近 N 天）。"""
    rows = conn.execute(
        """
        SELECT
            s.id,
            s.name,
            s.tier,
            s.enabled,
            s.error_count,
            COUNT(sh.id) AS checks,
            SUM(CASE WHEN sh.status = 'ok' THEN 1 ELSE 0 END) AS success_count,
            AVG(sh.response_time_ms) AS avg_response_ms,
            MAX(sh.date) AS last_check_date
        FROM sources s
        LEFT JOIN source_health sh
            ON s.id = sh.source_id
            AND sh.date >= date('now', ?)
        GROUP BY s.id
        ORDER BY s.tier ASC, s.name ASC
        """,
        (f"-{days} days",),
    ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        checks = int(data.get("checks") or 0)
        success = int(data.get("success_count") or 0)
        results.append(
            {
                "id": data["id"],
                "name": data["name"],
                "tier": data["tier"],
                "enabled": bool(data["enabled"]),
                "error_count": data.get("error_count", 0),
                "success_rate": round(success / checks, 3) if checks else None,
                "avg_response_ms": round(data["avg_response_ms"], 1) if data.get("avg_response_ms") else None,
                "last_check_date": data.get("last_check_date"),
            }
        )
    return results


def upsert_processed_article(conn: sqlite3.Connection, article: Article, *, selected: bool = False) -> None:
    """写入或更新经过管线处理的文章。"""
    row = _article_to_row(article)
    row["summary"] = article.summary or article.summary_raw or row.get("summary")
    row["is_selected"] = 1 if selected else 0
    insert_article(conn, row)


def mark_articles_selected(conn: sqlite3.Connection, articles: list[Article]) -> None:
    """批量标记 L2 精选文章。"""
    for article in articles:
        existing = get_article(conn, article.id)
        if existing:
            conn.execute(
                """
                UPDATE articles SET
                    is_selected = 1,
                    score = ?,
                    category = ?,
                    title_cn = ?,
                    summary = ?,
                    quality_level = ?
                WHERE id = ?
                """,
                (
                    article.score,
                    article.category.value if article.category else None,
                    article.title_cn,
                    article.summary or article.summary_raw,
                    article.quality_level.value if article.quality_level else None,
                    article.id,
                ),
            )
        else:
            if get_source(conn, article.source_id) is None:
                insert_source(
                    conn,
                    {
                        "id": article.source_id,
                        "name": article.source_name,
                        "url": article.url,
                        "type": "rss",
                        "tier": 1,
                        "language": article.language or "zh",
                        "enabled": 1,
                        "last_fetched_at": None,
                        "error_count": 0,
                    },
                )
            upsert_processed_article(conn, article, selected=True)

