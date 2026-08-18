"""技术指标计算（pandas 向量化）：MA/EMA/MACD/RSI/KDJ/BOLL"""
import pandas as pd


def compute(df: pd.DataFrame, settings: dict = None) -> pd.DataFrame:
    """输入 df 需含 date/open/high/low/close/volume（按时间升序），返回追加指标列的新 df。"""
    if df is None or df.empty:
        return pd.DataFrame()
    settings = settings or {}
    ma_windows = settings.get("ma_windows", [5, 10, 20, 60])
    rsi_period = settings.get("rsi_period", 14)
    kdj_period = settings.get("kdj_period", 9)
    boll_period = settings.get("boll_period", 20)
    boll_std = settings.get("boll_std", 2)

    d = df.copy()
    for c in ["open", "high", "low", "close", "volume"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.sort_values("date").reset_index(drop=True)

    # MA
    for w in ma_windows:
        d[f"ma{w}"] = d["close"].rolling(w).mean()

    # EMA / MACD
    ema12 = d["close"].ewm(span=12, adjust=False).mean()
    ema26 = d["close"].ewm(span=26, adjust=False).mean()
    d["macd_dif"] = ema12 - ema26
    d["macd_dea"] = d["macd_dif"].ewm(span=9, adjust=False).mean()
    d["macd_hist"] = 2 * (d["macd_dif"] - d["macd_dea"])

    # RSI（Wilder 平滑近似：ewm alpha=1/period）
    delta = d["close"].diff()
    up = delta.clip(lower=0)
    dn = (-delta).clip(lower=0)
    avg_up = up.ewm(alpha=1 / rsi_period, adjust=False).mean()
    avg_dn = dn.ewm(alpha=1 / rsi_period, adjust=False).mean()
    rs = avg_up / avg_dn.replace(0, pd.NA)
    d[f"rsi{rsi_period}"] = (100 - 100 / (1 + rs)).fillna(50)

    # KDJ
    llv = d["low"].rolling(kdj_period, min_periods=1).min()
    hhv = d["high"].rolling(kdj_period, min_periods=1).max()
    rsv = (d["close"] - llv) / (hhv - llv).replace(0, pd.NA) * 100
    d["kdj_k"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d["kdj_d"] = d["kdj_k"].ewm(alpha=1 / 3, adjust=False).mean()
    d["kdj_j"] = 3 * d["kdj_k"] - 2 * d["kdj_d"]

    # BOLL
    mid = d["close"].rolling(boll_period).mean()
    std = d["close"].rolling(boll_period).std(ddof=0)
    d["boll_mid"] = mid
    d["boll_upper"] = mid + boll_std * std
    d["boll_lower"] = mid - boll_std * std

    return d


def last_indicators(df: pd.DataFrame) -> dict:
    """取最近一行的全部指标，NaN 转 None"""
    if df is None or df.empty:
        return {}
    row = df.iloc[-1]
    out = {}
    for k in ["close", "ma5", "ma10", "ma20", "ma60", "macd_dif", "macd_dea", "macd_hist",
              "rsi14", "kdj_k", "kdj_d", "kdj_j", "boll_upper", "boll_mid", "boll_lower"]:
        v = row.get(k)
        out[k] = None if v is None or (isinstance(v, float) and v != v) else round(float(v), 4) if v is not None else None
    return out


def ma_alignment(df: pd.DataFrame, window: int = 5) -> str:
    """均线多空排列判断：多头(MA5>MA10>MA20>MA60) / 偏多 / 空头 / 偏空"""
    if df is None or len(df) < 2:
        return "数据不足"
    last = df.iloc[-1]
    ma5, ma10, ma20, ma60 = last.get("ma5"), last.get("ma10"), last.get("ma20"), last.get("ma60")
    if None in (ma5, ma10, ma20, ma60):
        return "数据不足"
    if ma5 > ma10 > ma20 > ma60:
        return "多头排列"
    if ma5 > ma20 > ma60:
        return "偏多"
    if ma5 < ma10 < ma20 < ma60:
        return "空头排列"
    if ma5 < ma20 < ma60:
        return "偏空"
    return "震荡"
