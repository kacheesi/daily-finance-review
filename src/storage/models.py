"""数据模型：dataclass 统一采集/分析结果契约"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CollectionResult:
    """当日全量采集结果（通道A agent写入 / 通道B akshare写入，schema一致）"""
    date: str
    indices: List[dict] = field(default_factory=list)          # 指数行情+涨跌+成交额
    market_sentiment: dict = field(default_factory=dict)       # 涨跌家数/涨停跌停/总成交额/主力资金
    sectors: List[dict] = field(default_factory=list)          # 行业板块
    stocks: List[dict] = field(default_factory=list)           # 自选股行情快照
    stock_history: Dict[str, List[dict]] = field(default_factory=dict)  # code -> 120日K线
    index_history: Dict[str, List[dict]] = field(default_factory=dict)  # code -> 80日K线(算MA)
    futures: List[dict] = field(default_factory=list)          # 期货行情
    crypto: List[dict] = field(default_factory=list)           # 币行情
    fundamentals: Dict[str, dict] = field(default_factory=dict)  # code -> PE/PB/ROE/营收增速/毛利率
    source_status: Dict[str, str] = field(default_factory=dict)  # 模块 -> ok/degraded/missing
    warnings: List[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """当日分析结果"""
    date: str
    market_score: int
    market_state: str
    risk_level: str
    sentiment_label: str
    indices_analysis: List[dict] = field(default_factory=list)  # 含技术指标
    stocks_analysis: List[dict] = field(default_factory=list)   # 含评级
    sectors_analysis: List[dict] = field(default_factory=list)
    futures_analysis: List[dict] = field(default_factory=list)
    crypto_analysis: List[dict] = field(default_factory=list)
    market_summary: str = ""       # AI市场总结(markdown)
    manager_view: str = ""         # 基金经理视角(markdown)
    data_sources: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
