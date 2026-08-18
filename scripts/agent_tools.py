"""通道A辅助脚本（WorkBuddy 自动化中 agent 使用）：
1) save：把 agent 用 MCP 工具取到的数据落盘为 collection.json
2) backfill-ai：把 agent 生成的 AI 总结（市场总结/经理视角 markdown）注入报告
用法:
  python scripts/agent_tools.py save --date 2026-08-18 --file /path/collection.json
  python scripts/agent_tools.py backfill-ai --date 2026-08-18 --summary /path/summary.md --view /path/view.md
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def save(date: str, file: str):
    from src.collector.orchestration import save_agent_collection
    with open(file, encoding="utf-8") as f:
        data = json.load(f)
    path = save_agent_collection(date, data)
    print("已落盘:", path)


def backfill_ai(date: str, summary: str, view: str):
    """注入 AI 总结并重渲染报告（复用 run_daily 的 ai-summary/ai-view 机制）"""
    from src.scheduler import run_daily
    report = run_daily(date, source="agent", skip_collect=True,
                       ai_summary=summary, ai_view=view)
    print("AI 总结已注入，报告:", report)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("save")
    p1.add_argument("--date", required=True)
    p1.add_argument("--file", required=True)
    p2 = sub.add_parser("backfill-ai")
    p2.add_argument("--date", required=True)
    p2.add_argument("--summary", required=True)
    p2.add_argument("--view", required=True)
    args = ap.parse_args()
    if args.cmd == "save":
        save(args.date, args.file)
    else:
        backfill_ai(args.date, args.summary, args.view)
