"""
ai-daily-system 启动入口

用法:
  uv run run.py serve     # 启动 API 服务 + 定时调度
  uv run run.py now        # 立即执行一次完整日报流程
  uv run run.py sources    # 检查信源健康状态
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import threading

import uvicorn

from src.config import get_settings
from src.scheduler.jobs import check_sources_health, daily_job, scheduler_loop


def serve() -> None:
    """启动 API 服务并在后台运行定时调度。"""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    if settings.scheduler_enabled:
        def _run_scheduler() -> None:
            asyncio.run(scheduler_loop(settings))

        threading.Thread(target=_run_scheduler, daemon=True).start()
    else:
        logging.getLogger(__name__).info("本地调度已禁用（云 Web 服务仅提供 Dashboard）")

    port = int(os.environ.get("PORT", settings.api_port))
    uvicorn.run(
        "src.output.api:app",
        host=settings.api_host,
        port=port,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ai-daily-system 启动入口")
    parser.add_argument(
        "command",
        choices=["serve", "now", "sources"],
        help="serve=API+调度, now=立即跑日报, sources=信源健康检查",
    )
    args = parser.parse_args()
    logging.basicConfig(level=get_settings().log_level)

    if args.command == "serve":
        serve()
    elif args.command == "now":
        result = asyncio.run(daily_job())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "sources":
        result = asyncio.run(check_sources_health())
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
