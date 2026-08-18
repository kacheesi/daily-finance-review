"""主流程编排：采集 → 分析 → AI总结(规则兜底) → 入库 → 渲染；含 catch-up 补执行。"""
import logging
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer import futures_crypto as fc
from src.analyzer import sector as sector_analyzer
from src.analyzer import stock_analyzer
from src.analyzer.indicators import compute, last_indicators
from src.analyzer.market_state import evaluate as evaluate_market
from src.ai.rule_summary import generate_manager_view, generate_market_summary
from src.collector.orchestration import collect_all
from src.report.renderer import render_report
from src.storage.database import Database
from src.utils.logger import get_logger
from src.utils.time_utils import is_trade_day, load_settings, load_watchlist

logger = get_logger("daily_review.scheduler")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(PROJECT_ROOT, "data", "reports")

_STATUS_LABEL = {
    "indices": "指数", "sentiment": "情绪", "sectors": "板块", "stocks": "自选股",
    "futures": "期货", "crypto": "币",
}


def run_daily(target_date: str = None, source: str = "script",
              skip_collect: bool = False, force_refresh: bool = False,
              ai_summary: str = None, ai_view: str = None) -> str:
    """执行单日完整流程。返回报告路径。
    ai_summary/ai_view: 外部(agent)生成的 Markdown 文件路径，注入后替代规则总结。"""
    d = target_date or datetime.now().strftime("%Y-%m-%d")
    db = Database()
    settings = load_settings()

    # 防重复：今日已执行且非强制/非AI注入 → 跳过（双通道互斥）
    if db.has_run(d) and not force_refresh and not (ai_summary or ai_view) and source != "catch_up":
        logger.info("%s 今日已执行，跳过（--force 可重跑）", d)
        existing = os.path.join(REPORT_DIR, "daily_report.html")
        return existing if os.path.exists(existing) else ""

    logger.info("===== 开始执行 %s (source=%s) =====", d, source)

    # 1. 采集（skip_collect 时读取已有 raw JSON）
    collection = collect_all(d, source=source, force_refresh=force_refresh) if not skip_collect else \
        collect_all(d, source="agent", force_refresh=False)
    ss = collection.get("source_status", {})

    # 2. 分析
    # 2.1 指数技术指标
    index_history = collection.get("index_history", {})
    for idx in collection.get("indices", []):
        kline = index_history.get(idx["code"], [])
        ind = compute(_df(kline), settings.get("technical", {}))
        li = last_indicators(ind)
        for k in ("ma5", "ma10", "ma20", "ma60"):
            idx[k] = li.get(k)
        idx["ma_alignment"] = _ma_align(li)

    # 2.2 市场状态评分
    market = evaluate_market(collection, settings)
    market["sentiment"] = collection.get("market_sentiment", {})

    # 2.3 行业板块
    sectors = sector_analyzer.analyze_sectors(collection.get("sectors", []))

    # 2.4 自选股
    stock_history = collection.get("stock_history", {})
    stock_indicators = {}
    for code, kline in stock_history.items():
        stock_indicators[code] = compute(_df(kline), settings.get("technical", {}))
    stocks = stock_analyzer.analyze_watchlist(
        collection.get("stocks", []), stock_history,
        collection.get("fundamentals", {}), settings)

    # 2.5 期货 / 币
    futures = fc.analyze_futures(collection.get("futures", []))
    crypto = fc.analyze_crypto(collection.get("crypto", []), collection.get("crypto_history", {}))

    # 3. AI 总结（规则兜底；注入 ai_summary/ai_view 时使用外部生成内容）
    if ai_summary and os.path.exists(ai_summary):
        market_summary = open(ai_summary, encoding="utf-8").read()
    else:
        market_summary = generate_market_summary(market, collection.get("indices", []),
                                                 sectors, stocks, futures, crypto)
    if ai_view and os.path.exists(ai_view):
        manager_view = open(ai_view, encoding="utf-8").read()
    else:
        manager_view = generate_manager_view(market, sectors, stocks)

    # 4. 组装分析结果
    analysis = {
        "date": d,
        "market_score": market["market_score"],
        "market_state": market["market_state"],
        "risk_level": market["risk_level"],
        "sentiment_label": market["sentiment_label"],
        "market_sentiment": collection.get("market_sentiment", {}),
        "indices": collection.get("indices", []),
        "sectors": sectors,
        "stocks": stocks,
        "futures": futures,
        "crypto": crypto,
        "stock_history": stock_history,
        "stock_indicators": stock_indicators,
        "market_summary": market_summary,
        "manager_view": manager_view,
        "warnings": collection.get("warnings", []),
        "data_sources": ss,
        "data_sources_label": _src_label(ss),
    }

    # 5. 入库
    db.start_run(d, source)
    try:
        _persist(db, d, analysis, collection)
    except Exception as e:
        logger.error("入库失败: %s", e)

    # 6. 渲染
    report_path = render_report(analysis)

    # 6.1 桌面同步（最新报告自动复制到桌面文件夹 + zip）
    try:
        from src.utils.desktop_sync import sync as desktop_sync
        desktop_sync()
    except Exception as e:
        logger.warning("桌面同步失败: %s", e)

    # 7. run_log
    has_missing = any(v in ("missing",) for v in ss.values()) or bool(collection.get("warnings"))
    db.finish_run(d, "partial" if has_missing else "success", report_path)
    logger.info("===== %s 执行完成 status=%s =====", d, "partial" if has_missing else "success")
    return report_path


def catch_up(target_date: str = None) -> list:
    """补执行：从最近成功日之后逐日补到 target_date（今日）。返回已执行日期列表。"""
    db = Database()
    now = datetime.now()
    today = now.date()
    target = date.fromisoformat(target_date) if target_date else today

    last = db.get_latest_run()
    start = date.fromisoformat(last) + timedelta(days=1) if last else target
    if target_date:
        # 显式指定日期时，从该日与 last+1 的较早者开始补
        start = min(start, target)
    executed = []
    d = start
    while d <= target:
        ds = d.strftime("%Y-%m-%d")
        if not is_trade_day(d):
            logger.info("%s 非交易日，跳过", ds)
            d += timedelta(days=1)
            continue
        # 今日未到 17:00 不提前跑
        if d == today and now.hour < 17 and not target_date:
            logger.info("今日尚未到 17:00，跳过 %s", ds)
            break
        if db.has_run(ds):
            d += timedelta(days=1)
            continue
        try:
            run_daily(ds, source="catch_up")
            executed.append(ds)
        except Exception as e:
            logger.error("补执行 %s 失败: %s", ds, e)
            db.start_run(ds, "catch_up")
            db.finish_run(ds, "failed", error_msg=str(e)[:500])
        d += timedelta(days=1)
    return executed


def _persist(db: Database, d: str, analysis: dict, collection: dict) -> None:
    # 先清当日数据再入库，避免残留已删除/变更的标的（数据一致性）
    for t in ("daily_indices", "daily_sectors", "daily_stocks", "daily_futures", "daily_crypto"):
        db.clear_date(t, d)
    db.upsert_market({
        "date": d, "market_score": analysis["market_score"], "state": analysis["market_state"],
        "risk_level": analysis["risk_level"],
        "up_count": analysis["market_sentiment"].get("up_count"),
        "down_count": analysis["market_sentiment"].get("down_count"),
        "limit_up": analysis["market_sentiment"].get("limit_up"),
        "limit_down": analysis["market_sentiment"].get("limit_down"),
        "total_amount": analysis["market_sentiment"].get("total_amount"),
        "main_net_inflow": analysis["market_sentiment"].get("main_net_inflow"),
        "sentiment": analysis["sentiment_label"],
    })
    db.upsert_indices(d, [{k: i.get(k) for k in
                           ["code", "name", "close", "pct_change", "amount", "main_net_inflow",
                            "ma5", "ma10", "ma20", "ma60"]} for i in analysis["indices"]])
    db.upsert_sectors(d, [{k: s.get(k) for k in
                           ["code", "name", "pct_change", "main_net_inflow", "rank", "strength",
                            "consecutive_up_days", "heat"]} for s in analysis["sectors"]])
    db.upsert_stocks(d, [{k: s.get(k) for k in
                          ["code", "name", "close", "pct_change", "volume", "turnover_rate",
                           "market_cap", "pe", "pb", "main_net_inflow",
                           "ma5", "ma10", "ma20", "ma60", "macd_dif", "macd_dea", "macd_hist",
                           "rsi14", "kdj_k", "kdj_d", "kdj_j",
                           "boll_upper", "boll_mid", "boll_lower",
                           "trend", "tech_state", "risk_level", "fundamental_grade", "grade",
                           "roe", "revenue_yoy", "profit_yoy", "gross_margin"]}
                         for s in analysis["stocks"]])
    db.upsert_futures(d, analysis["futures"])
    db.upsert_crypto(d, analysis["crypto"])
    db.save_report(d, analysis["market_summary"], analysis["manager_view"],
                   os.path.join("data", "reports", f"{d}.html"), collection.get("source_status", {}))


def _df(kline: list):
    import pandas as pd
    return pd.DataFrame(kline) if kline else pd.DataFrame()


def _ma_align(li: dict) -> str:
    ma5, ma10, ma20, ma60 = li.get("ma5"), li.get("ma10"), li.get("ma20"), li.get("ma60")
    if None in (ma5, ma10, ma20, ma60):
        return "数据不足"
    if ma5 > ma10 > ma20 > ma60:
        return "多头排列"
    if ma5 < ma10 < ma20 < ma60:
        return "空头排列"
    if ma5 > ma20 > ma60:
        return "偏多"
    if ma5 < ma20 < ma60:
        return "偏空"
    return "震荡"


def _src_label(ss: dict) -> str:
    labels = []
    for k, v in ss.items():
        label = _STATUS_LABEL.get(k, k)
        labels.append(f"{label}:{'✓' if v == 'ok' else ('⚠' if v == 'missing' else '—')}")
    return " ".join(labels)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="每日金融复盘")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD")
    ap.add_argument("--source", default="script", choices=["script", "agent", "catch_up"])
    ap.add_argument("--skip-collect", action="store_true", help="跳过采集，读取已有 raw JSON")
    ap.add_argument("--force", action="store_true", help="强制重新采集")
    ap.add_argument("--ai-summary", help="注入外部生成的AI市场总结(md)")
    ap.add_argument("--ai-view", help="注入外部生成的AI经理视角(md)")
    ap.add_argument("--catchup", action="store_true", help="执行补跑")
    args = ap.parse_args()

    if args.catchup:
        done = catch_up(args.date)
        print("补执行完成:", done or "无需补跑")
    else:
        p = run_daily(args.date, source=args.source, skip_collect=args.skip_collect,
                      force_refresh=args.force, ai_summary=args.ai_summary, ai_view=args.ai_view)
        print("报告:", p)
