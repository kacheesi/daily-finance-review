#!/usr/bin/env python3
"""每日复盘主入口（通道B：Windows 任务计划 / Cron / 开机补跑）
用法:
  python run_daily.py                 # 今日全流程（采集+分析+报告）
  python run_daily.py --catchup       # 补执行缺失交易日（开机后运行）
  python run_daily.py --date 2026-08-18 --source agent --skip-collect
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scheduler import catch_up, run_daily  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger("daily_review.entry")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="每日金融复盘系统入口")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD（默认今日）")
    ap.add_argument("--source", default="script", choices=["script", "agent", "catch_up"],
                    help="数据来源: script=自动采集(默认) / agent=读agent落盘JSON")
    ap.add_argument("--skip-collect", action="store_true", help="跳过采集，仅分析已有数据")
    ap.add_argument("--force", action="store_true", help="强制重新采集")
    ap.add_argument("--ai-summary", help="注入外部生成的AI市场总结(md)")
    ap.add_argument("--ai-view", help="注入外部生成的AI经理视角(md)")
    ap.add_argument("--catchup", action="store_true", help="补执行模式（开机后调用）")
    args = ap.parse_args()

    try:
        if args.catchup:
            done = catch_up(args.date)
            print("补执行完成:", done if done else "无需补跑")
        else:
            report = run_daily(args.date, source=args.source, skip_collect=args.skip_collect,
                               force_refresh=args.force, ai_summary=args.ai_summary,
                               ai_view=args.ai_view)
            print("报告已生成:", report)
    except Exception as e:
        logger.exception("运行失败")
        print("ERROR:", e)
        sys.exit(1)
