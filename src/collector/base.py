"""统一数据契约：通道A(agent/MCP)与通道B(akshare)写入 data/raw/<date>/collection.json 的标准结构。
分析层只消费该结构，对数据来源透明。"""
import os

RAW_SCHEMA_VERSION = "1.0"

# collection.json 顶层字段
REQUIRED_TOP = ["date", "indices", "market_sentiment", "sectors", "stocks",
                "stock_history", "index_history", "futures", "crypto",
                "fundamentals", "source_status", "warnings"]

# 各子模块字段约定（分析层依赖，缺失字段容忍为 None）
INDEX_FIELDS = ["code", "name", "close", "pct_change", "amount"]
SENTIMENT_FIELDS = ["up_count", "down_count", "limit_up", "limit_down",
                    "total_amount", "main_net_inflow", "prev_total_amount"]
STOCK_FIELDS = ["code", "name", "close", "pct_change", "volume", "turnover_rate",
                "market_cap", "pe", "pb", "main_net_inflow"]
KLINE_FIELDS = ["date", "open", "high", "low", "close", "volume", "amount"]
SECTOR_FIELDS = ["code", "name", "pct_change", "main_net_inflow"]
FUTURE_FIELDS = ["symbol", "name", "close", "pct_change"]
CRYPTO_FIELDS = ["symbol", "name", "price", "pct_change", "high_24h", "low_24h", "volume_24h"]
FUNDAMENTAL_FIELDS = ["pe", "pb", "roe", "revenue_yoy", "profit_yoy", "gross_margin", "total_mv"]


def raw_dir_for(project_root: str, date: str) -> str:
    return os.path.join(project_root, "data", "raw", date)


def collection_path(project_root: str, date: str) -> str:
    return os.path.join(raw_dir_for(project_root, date), "collection.json")


def load_collection(path: str) -> dict:
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_collection(data: dict, path: str) -> None:
    import json
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
