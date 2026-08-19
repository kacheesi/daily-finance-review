"""采集编排：通道A(读 agent/MCP 落盘的 collection.json) 与 通道B(东财/腾讯/新浪/CoinGecko 实时取数)。
通道B优先级：东财(push2delay,含主力资金/A50) → 腾讯(行情K线) → 新浪(情绪/期货) → AkShare(备用) → 缺失标记。"""
import json
import logging
import os

from src.collector import coingecko_source, eastmoney_source, sina_source, tencent_source
from src.collector.base import collection_path, save_collection
from src.utils.time_utils import load_market_codes, load_settings, load_watchlist

logger = logging.getLogger("daily_review.collector.orchestration")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 用户行业 -> 板块名称匹配关键词（东财细分行业/新浪行业通用）
SECTOR_MATCH = {
    "消费": ["食品饮料", "零售", "家用电器", "消费", "白酒", "饮料"],
    "白酒": ["白酒", "酿酒", "啤酒", "酒"],
    "食品饮料": ["食品", "饮料", "乳品", "调味", "休闲食品", "预制"],
    "医药医疗": ["医药", "医疗", "生物", "制药", "中药", "化学", "服务"],
    "AI人工智能": ["人工智能", "软件", "计算机", "IT服务", "互联网", "AI", "算力", "数据"],
    "半导体": ["半导体", "集成电路", "芯片", "元件"],
    "存储芯片": ["存储", "半导体材料", "半导体设备"],
    "机器人": ["机器人", "自动化", "通用设备", "工控"],
    "新能源": ["光伏", "风电", "电池", "新能源", "电力设备", "储能"],
    "金融": ["银行", "保险", "证券", "多元金融", "金融"],
    "地产": ["房地产", "地产", "物业"],
    "有色金属": ["有色", "贵金属", "工业金属", "小金属", "铜", "铝", "黄金"],
    "军工": ["军工", "航天", "航空", "国防", "兵器"],
    "电力能源": ["电力", "煤炭", "石油", "燃气", "能源", "电网"],
}


def _empty_collection(date: str) -> dict:
    return {
        "schema_version": "1.0",
        "date": date,
        "indices": [], "market_sentiment": {}, "sectors": [],
        "stocks": [], "stock_history": {}, "index_history": {},
        "futures": [], "crypto": [], "fundamentals": {},
        "crypto_history": {}, "asia_indices": [],
        "source_status": {}, "warnings": [],
    }


def collect_all(date: str, source: str = "script", force_refresh: bool = False) -> dict:
    """统一采集入口。
    - source='agent': 读取 data/raw/<date>/collection.json（agent 用 MCP 写入）；缺失时回退脚本采集。
    - source='script': 东财/腾讯/新浪/CoinGecko 实时采集。
    """
    path = collection_path(PROJECT_ROOT, date)

    if source == "agent" and not force_refresh:
        if os.path.exists(path):
            try:
                data = json.load(open(path, encoding="utf-8"))
                data["date"] = date
                logger.info("读取 agent 通道数据: %s", path)
                return data
            except Exception as e:
                logger.warning("agent 数据读取失败(%s)，回退脚本采集", e)
        else:
            logger.info("未找到 agent 数据 %s，回退脚本采集", path)

    return _collect_with_script(date)


def _collect_with_script(date: str) -> dict:
    codes = load_market_codes()
    watchlist = load_watchlist()
    data = _empty_collection(date)
    # 云端模式（GitHub Actions 海外执行）：腾讯/新浪优先（海外可达性高），东财兜底
    cloud = os.environ.get("DAILY_REVIEW_CLOUD") == "1" or load_settings().get("cloud_mode", False)

    # ---- 1. 指数（本地:东财优先含A50/主力资金；云端:腾讯优先） ----
    primary_idx, fallback_idx = ((tencent_source, eastmoney_source) if cloud
                                 else (eastmoney_source, tencent_source))
    ok, indices = primary_idx.fetch_index_spot(codes["indices"])
    if not ok or not any(i.get("close") for i in indices):
        ok2, indices2 = fallback_idx.fetch_index_spot(codes["indices"])
        if ok2 and indices2:
            indices, ok = indices2, True
            data["warnings"].append(f"{primary_idx.__name__}指数不可用，已用{fallback_idx.__name__}兜底")
    data["indices"] = indices
    data["source_status"]["indices"] = "ok" if ok and any(i.get("close") for i in indices) else "missing"
    if not any(i.get("close") for i in indices):
        data["warnings"].append("指数数据缺失")
    # 指数K线：腾讯优先，A50 等腾讯不支持的用东财 kline
    for idx in codes["indices"]:
        k_ok, kline = tencent_source.fetch_index_kline(idx["code"])
        if not k_ok or not kline:
            k_ok, kline = eastmoney_source.fetch_index_kline(idx["code"])
        data["index_history"][idx["code"]] = kline if k_ok else []
        if not k_ok:
            data["warnings"].append(f"指数K线缺失: {idx['name']}")

    # ---- 2. 市场情绪（本地:东财全A统计含主力资金；云端:新浪） ----
    if cloud:
        ok, sentiment = sina_source.fetch_market_sentiment()
        if not ok or sentiment.get("up_count") is None:
            ok, sentiment = eastmoney_source.fetch_market_sentiment()
            data["warnings"].append("新浪情绪统计不可用，已用东财兜底")
    else:
        ok, sentiment = eastmoney_source.fetch_market_sentiment()
        if not ok or sentiment.get("up_count") is None:
            ok, sentiment = sina_source.fetch_market_sentiment()
            data["warnings"].append("东财情绪统计不可用，已用新浪兜底")
    data["market_sentiment"] = sentiment
    data["source_status"]["sentiment"] = "ok" if ok and sentiment.get("up_count") is not None else "missing"
    if sentiment.get("main_net_inflow") is None:
        data["warnings"].append("主力资金数据缺失，评分将归一化处理")

    # ---- 3. 行业板块（本地:东财含资金流；云端:新浪） ----
    if cloud:
        ok, raw_sectors = sina_source.fetch_sectors()
        if not ok or not raw_sectors:
            ok, raw_sectors = eastmoney_source.fetch_sectors()
            data["warnings"].append("新浪行业板块不可用，已用东财兜底")
    else:
        ok, raw_sectors = eastmoney_source.fetch_sectors()
        if not ok or not raw_sectors:
            ok, raw_sectors = sina_source.fetch_sectors()
            data["warnings"].append("东财行业板块不可用，已用新浪兜底")
    data["sectors"] = _map_sectors(raw_sectors) if ok else []
    data["source_status"]["sectors"] = "ok" if data["sectors"] else "missing"
    if data["sectors"]:
        missing = [s for s in data["sectors"] if s.get("pct_change") is None]
        if missing:
            data["warnings"].append(f"板块无对应数据: {','.join(s['name'] for s in missing)}")

    # ---- 4. 自选股（本地:东财含主力资金；云端:腾讯） ----
    primary_stk, fallback_stk = ((tencent_source, eastmoney_source) if cloud
                                 else (eastmoney_source, tencent_source))
    ok, stocks = primary_stk.fetch_stocks_spot(watchlist)
    if not ok or not any(s.get("close") for s in stocks):
        ok2, stocks2 = fallback_stk.fetch_stocks_spot(watchlist)
        if ok2 and stocks2:
            stocks, ok = stocks2, True
            data["warnings"].append(f"{primary_stk.__name__}自选股行情不可用，已用{fallback_stk.__name__}兜底")
    data["stocks"] = stocks
    data["source_status"]["stocks"] = "ok" if ok and any(s.get("close") for s in stocks) else "missing"
    for s in watchlist:
        code = s["code"]
        k_ok, kline = tencent_source.fetch_kline(code)
        data["stock_history"][code] = kline if k_ok else []
        if not k_ok:
            data["warnings"].append(f"个股K线缺失: {code}")
        # 基本面（本地:东财优先；云端:新浪优先，东财 datacenter 海外可达性不确定）
        f_ok, fund = (sina_source.fetch_fundamental(code) if cloud
                      else eastmoney_source.fetch_fundamental(code))
        if not f_ok or not any(fund.values()):
            f_ok2, fund2 = (eastmoney_source.fetch_fundamental(code) if cloud
                            else sina_source.fetch_fundamental(code))
            if f_ok2:
                fund = {**fund, **{k: v for k, v in fund2.items() if v is not None}}
        spot = next((x for x in stocks if x["code"] == code), None)
        if spot:
            if fund.get("pe") is None:
                fund["pe"] = spot.get("pe")
            if fund.get("pb") is None:
                fund["pb"] = spot.get("pb")
            if fund.get("total_mv") is None:
                fund["total_mv"] = spot.get("market_cap")
        data["fundamentals"][code] = fund

    # ---- 5. 期货（新浪） ----
    ok, futures = sina_source.fetch_futures(codes["futures"])
    data["futures"] = futures
    data["source_status"]["futures"] = "ok" if ok else "missing"

    # ---- 6. 币（CoinGecko） ----
    ok, crypto = coingecko_source.fetch_crypto(codes["crypto"])
    data["crypto"] = crypto
    data["source_status"]["crypto"] = "ok" if ok and any(c.get("price") for c in crypto) else "missing"
    for c in codes["crypto"]:
        k_ok, kline = coingecko_source.fetch_crypto_klines(c["symbol"])
        if k_ok:
            data["crypto_history"][c["symbol"]] = kline

    # ---- 7. 亚太指数（日韩，东财国际指数） ----
    asia_ok, asia = eastmoney_source.fetch_asia_indices(codes.get("asia_indices", []))
    data["asia_indices"] = asia
    data["source_status"]["asia"] = "ok" if asia_ok else "missing"
    if asia_ok:
        for a in asia:
            k_ok2, kline2 = eastmoney_source.fetch_asia_kline(a["code"])
            a["kline"] = kline2 if k_ok2 else []
    else:
        data["warnings"].append("亚太指数(日韩)数据缺失")

    save_collection(data, collection_path(PROJECT_ROOT, date))
    logger.info("脚本采集完成 -> %s (status=%s)", collection_path(PROJECT_ROOT, date), data["source_status"])
    return data


def _map_sectors(raw_sectors: list) -> list:
    """把来源板块（东财细分/新浪行业）收敛到用户关注的14行业。
    匹配到多个时取涨幅最大者作为代表（携带资金流）。"""
    targets = load_market_codes()["sectors"]
    picked = {}
    for target in targets:
        keys = SECTOR_MATCH.get(target, [target])
        candidates = []
        for s in raw_sectors:
            name = s.get("name", "")
            if any(k in name for k in keys):
                candidates.append(s)
        if not candidates:
            picked[target] = {"code": target, "name": target, "pct_change": None,
                              "main_net_inflow": None, "amount": None,
                              "leader": None, "leader_pct": None, "total_count": None}
            continue
        best = max(candidates, key=lambda s: s.get("pct_change") or -999)
        picked[target] = {**best, "name": target,
                          "leader": best.get("leader"),
                          "leader_pct": best.get("leader_pct")}
        picked[target]["total_count"] = len(candidates)
    return sorted(picked.values(), key=lambda s: -(s.get("pct_change") or 0))


def save_agent_collection(date: str, data: dict) -> str:
    """通道A：agent 用 MCP 取数后调用本函数落盘"""
    data["date"] = date
    path = collection_path(PROJECT_ROOT, date)
    save_collection(data, path)
    logger.info("agent 数据已落盘: %s", path)
    return path
