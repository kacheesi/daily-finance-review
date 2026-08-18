"""报告渲染：组装 context → Jinja2 模板 → daily_report.html + 归档"""
import json
import logging
import os
import shutil
from datetime import datetime

import markdown as md_lib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.report.charts import build_charts_js

logger = logging.getLogger("daily_review.report.renderer")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "src", "report", "templates")
REPORT_DIR = os.path.join(PROJECT_ROOT, "data", "reports")

ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"


def fmt_amount(v):
    if v is None:
        return "—"
    v = float(v)
    if v >= 1e12:
        return f"{v / 1e12:.2f}万亿"
    if v >= 1e8:
        return f"{v / 1e8:.0f}亿"
    if v >= 1e4:
        return f"{v / 1e4:.0f}万"
    return f"{v:.0f}"


def _state_badge(state: str) -> str:
    if "强势" in state:
        return "badge-strong"
    if "震荡" in state or "整理" in state:
        return "badge-osc"
    if "恐慌" in state or "风险" in state:
        return "badge-danger"
    return "badge-weak"


def render_report(analysis: dict) -> str:
    """analysis: 分析结果 dict（含 date/market_*/indices/sectors/stocks/futures/crypto/summaries）。
    返回 HTML 文件绝对路径。"""
    os.makedirs(REPORT_DIR, exist_ok=True)

    sentiment = analysis.get("market_sentiment", {})
    stocks = analysis.get("stocks", [])
    indices = analysis.get("indices", [])

    # K线数据注入（供 candlestick 图）
    for s in stocks:
        s["kline"] = analysis.get("stock_history", {}).get(s["code"], [])
        ind = analysis.get("stock_indicators", {}).get(s["code"])
        if hasattr(ind, "tail"):
            s["kline_indicators"] = ind.tail(120).to_dict("records")
        else:
            s["kline_indicators"] = []

    data = {
        "date": analysis["date"],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_score": analysis.get("market_score"),
        "market_state": analysis.get("market_state"),
        "risk_level": analysis.get("risk_level"),
        "sentiment_label": analysis.get("sentiment_label"),
        "badge_class": _state_badge(analysis.get("market_state", "")),
        "up_count": sentiment.get("up_count"),
        "down_count": sentiment.get("down_count"),
        "limit_up": sentiment.get("limit_up"),
        "limit_down": sentiment.get("limit_down"),
        "total_amount": sentiment.get("total_amount"),
        "indices": indices,
        "sectors": analysis.get("sectors", []),
        "stocks": stocks,
        "futures": analysis.get("futures", []),
        "crypto": analysis.get("crypto", []),
        "market_sentiment": sentiment,
        "market_summary_html": md_lib.markdown(analysis.get("market_summary", ""), extensions=["tables"]),
        "manager_view_html": md_lib.markdown(analysis.get("manager_view", ""), extensions=["tables"]),
        "warnings": "；".join(analysis.get("warnings", []))[:400],
        "data_sources": analysis.get("data_sources_label", ""),
        "echarts_cdn": ECHARTS_CDN,
        "data_json": json.dumps({
            "indices": indices, "sectors": analysis.get("sectors", []),
            "stocks": stocks, "futures": analysis.get("futures", []),
            "crypto": analysis.get("crypto", []), "market_sentiment": sentiment,
        }, ensure_ascii=False, default=str),
        "charts_js": build_charts_js({
            "market_score": analysis.get("market_score"),
            "indices": indices, "sectors": analysis.get("sectors", []),
            "stocks": stocks, "futures": analysis.get("futures", []),
            "crypto": analysis.get("crypto", []), "market_sentiment": sentiment,
        }),
    }

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))
    env.filters["fmt_amount"] = fmt_amount
    data["fmt_amount"] = fmt_amount  # 模板内以函数形式调用
    html = env.get_template("daily_report.html.j2").render(**data)

    latest = os.path.join(REPORT_DIR, "daily_report.html")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(html)
    archive = os.path.join(REPORT_DIR, f"{analysis['date']}.html")
    shutil.copyfile(latest, archive)
    logger.info("报告已生成: %s (+ 归档 %s)", latest, archive)
    return latest
