# -*- coding: utf-8 -*-
"""
数据获取模块

主数据源：腾讯行情（qt.gtimg.cn / web.ifzq.gtimg.cn）
  - 国内境外均可访问、免费无 key、响应快、无限流
  - 覆盖美股 / 港股 / A股指数 / 美股指数 / 港股指数 / VIX / 黄金 / 原油
辅助源：yfinance（美债收益率、美元指数、港股股息率），失败自动降级为 —

注意腾讯代码差异：
  美股实时行情 usNVDA  →  K线需带后缀 usNVDA.OQ
  港股实时行情 hk00700 →  K线同为 hk00700
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import requests

QUOTE_URL = "http://qt.gtimg.cn/q={codes}"
KLINE_URL = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,320,qfq"

# VIX 权威源：CBOE 官方接口（免费、无 key、延迟15分钟）
# 注意：腾讯 usVIX 存在滞后问题（实测曾返回历史值 21.67，而官方为 14.53），仅作兜底
CBOE_VIX_URL = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _f(v: Any, default: float | None = None) -> float | None:
    try:
        s = str(v).strip()
        if not s:
            return default
        return float(s)
    except (TypeError, ValueError):
        return default


def _quote_codes(codes: list[str]) -> dict[str, list[str]]:
    """批量拉取实时行情，返回 {代码: 字段列表}"""
    if not codes:
        return {}
    try:
        r = requests.get(QUOTE_URL.format(codes=",".join(codes)),
                         headers=HEADERS, timeout=20)
        r.encoding = "gbk"
    except Exception as e:
        print(f"[fetcher] 行情请求失败: {e}")
        return {}

    out: dict[str, list[str]] = {}
    for line in r.text.split(";"):
        if '="' not in line:
            continue
        key = line.split("=")[0].strip().lstrip("v_").replace("v_", "")
        try:
            val = line.split('"')[1]
        except IndexError:
            continue
        if not val:
            continue
        # 普通股票/指数用 ~ 分隔；外盘期货（hf_）用 , 分隔
        out[key] = val.split("~") if "~" in val else val.split(",")
    return out


def _parse_quote(f: list[str], market: str) -> dict[str, Any]:
    """解析腾讯行情字段 → 现价/涨跌幅/PE/市值"""
    if not f:
        return {}

    # 外盘期货（hf_*）字段少且用逗号分隔：[0]现价 [1]涨跌幅 [7]昨收
    if market == "fut":
        return {"price": _f(f[0]), "chg": _f(f[1]), "pe": None, "mcap": None}

    if len(f) < 33:
        return {}

    price = _f(f[3])
    chg = _f(f[32])
    pe = _f(f[39]) if len(f) > 39 else None

    mcap = None
    if market == "us":
        v45 = _f(f[45]) if len(f) > 45 else None
        if v45:                      # 单位：亿美元
            mcap = v45 * 1e8
        else:
            # ETF 等无市值字段时，用 总股本 × 现价 估算
            shares = _f(f[62]) if len(f) > 62 else None
            if shares and price:
                mcap = price * shares
    elif market == "hk":
        shares = _f(f[69]) if len(f) > 69 else None
        if shares and price:         # 市值 = 现价 × 总股本
            mcap = price * shares

    return {"price": price, "chg": chg, "pe": pe, "mcap": mcap}


def _kline_changes(code: str) -> dict[str, float | None]:
    """从日K线计算 5日 / 20日 / 今年以来涨跌幅"""
    try:
        r = requests.get(KLINE_URL.format(code=code), headers=HEADERS, timeout=20)
        j = r.json()
        node = (j.get("data") or {}).get(code)
        if not node:
            return {}
        arr = node.get("qfqday") or node.get("day") or []
        if len(arr) < 2:
            return {}
        # 每条: [日期, 开, 收, 高, 低, 量]
        closes = [(a[0], _f(a[2])) for a in arr if _f(a[2]) is not None]
    except Exception:
        return {}

    if len(closes) < 2:
        return {}
    last_date, price = closes[-1]

    def chg(n: int) -> float | None:
        if len(closes) > n:
            base = closes[-(n + 1)][1]
            if base:
                return (price / base - 1) * 100
        return None

    # 今年以来：以去年最后一个交易日收盘价为基准
    ytd = None
    try:
        year = int(str(last_date)[:4])
        prior = [c for c in closes if str(c[0]) < f"{year}-01-01"]
        if prior:
            base = prior[-1][1]
            if base:
                ytd = (price / base - 1) * 100
    except Exception:
        pass

    return {"chg5": chg(5), "chg20": chg(20), "chg_ytd": ytd, "date": last_date}


def _realtime_code(kline_code: str) -> str:
    """K线代码 → 实时行情代码（美股去掉 .OQ/.N/.AM 后缀）"""
    if "." in kline_code:
        return kline_code.rsplit(".", 1)[0]
    return kline_code


def _yfinance_extras(cfg) -> dict[str, Any]:
    """用 yfinance 补充美债收益率、美元指数、港股股息率。失败返回空。"""
    out: dict[str, Any] = {"treasury": [], "usd_index": None, "div": {}}
    try:
        import pandas as pd
        import yfinance as yf
    except ImportError:
        print("[fetcher] 未安装 yfinance，跳过美债/股息率补充")
        return out

    # --- 美债收益率 + 美元指数 ---
    codes = [c for c, _ in cfg.TREASURY] + [cfg.USD_INDEX_CODE]
    try:
        raw = yf.download(codes, period="5d", group_by="ticker",
                          progress=False, threads=True)
        multi = isinstance(raw.columns, pd.MultiIndex)

        def last_close(code: str) -> float | None:
            try:
                df = raw[code] if multi else raw
                s = df["Close"].dropna()
                return float(s.iloc[-1]) if not s.empty else None
            except Exception:
                return None

        for code, name in cfg.TREASURY:
            out["treasury"].append({"name": name, "yield": last_close(code)})
        out["usd_index"] = last_close(cfg.USD_INDEX_CODE)
    except Exception as e:
        print(f"[fetcher] 美债数据获取失败（不影响主流程）: {e}")

    # --- 港股股息率（腾讯代码 hk00700 → Yahoo 0700.HK）---
    for code, _, _ in cfg.HK_STOCKS:
        try:
            d = (yf.Ticker(code[3:] + ".HK").info or {}).get("dividendYield")
            if isinstance(d, (int, float)):
                out["div"][code] = d * 100
        except Exception:
            pass
    return out


def _fetch_vix(idx_q: dict, cfg) -> dict[str, Any]:
    """
    VIX 波动率指数。

    优先用 CBOE 官方接口（权威值）。腾讯的 usVIX 经实测存在滞后
    （曾返回 2 月的历史值 21.67，而官方当日为 14.53），因此仅作兜底，
    且降级时会在返回中标记 source 以便排查。
    """
    try:
        r = requests.get(CBOE_VIX_URL, headers=HEADERS, timeout=15)
        d = r.json()["data"]
        price = _f(d.get("current_price") or d.get("close"))
        if price:
            return {
                "price": price,
                "chg": _f(d.get("price_change_percent")),
                "source": "cboe",
            }
    except Exception as e:
        print(f"[fetcher] CBOE VIX 获取失败，降级腾讯: {str(e)[:50]}")

    fv = idx_q.get(cfg.VIX_CODE)
    pv = _parse_quote(fv, "idx") if fv else {}
    return {
        "price": pv.get("price"),
        "chg": pv.get("chg"),
        "source": "tencent-fallback",
    }


def _fetch_etfs(cfg) -> dict[str, list[dict[str, Any]]]:
    """
    拉取板块 / 主题 / 宏观 ETF，并计算 52 周区间分位与距高点回撤。
    这些 ETF 的当日涨跌是判断板块轮动与风险偏好的直接依据。
    """
    codes = ([c for c, _ in cfg.SECTOR_ETFS] +
             [c for c, _ in cfg.THEME_ETFS] +
             [c for c, _ in cfg.MACRO_ETFS])
    q = _quote_codes(codes)

    def build(lst):
        rows = []
        for code, label in lst:
            f = q.get(code)
            if not f or len(f) < 33:
                continue
            price = _f(f[3])
            chg = _f(f[32])
            hi = _f(f[48]) if len(f) > 48 else None
            lo = _f(f[49]) if len(f) > 49 else None
            pos52 = off_high = None
            if price and hi and lo and hi > lo:
                pos52 = (price - lo) / (hi - lo) * 100      # 52 周区间分位（0=低点, 100=高点）
            if price and hi:
                off_high = (price / hi - 1) * 100           # 距 52 周高点回撤
            rows.append({"code": code, "name": label, "price": price,
                         "chg": chg, "pos52": pos52, "off_high": off_high})
        return rows

    return {"sector": build(cfg.SECTOR_ETFS),
            "theme": build(cfg.THEME_ETFS),
            "macro": build(cfg.MACRO_ETFS)}


def fetch_all(cfg) -> dict[str, Any]:
    """
    拉取全部数据，返回结构化字典供 builder 使用。
    """
    result: dict[str, Any] = {}

    # ---------- 1. 指数与 VIX ----------
    idx_codes = [c for grp in cfg.INDICES for c, _ in grp["items"]] + [cfg.VIX_CODE]
    idx_q = _quote_codes(idx_codes)

    indices = []
    for grp in cfg.INDICES:
        items = []
        for code, name in grp["items"]:
            f = idx_q.get(code)
            p = _parse_quote(f, "idx") if f else {}
            items.append({"name": name, "price": p.get("price"), "chg": p.get("chg")})
        indices.append({"market": grp["market"], "label": grp["label"], "items": items})
    result["indices"] = indices

    result["vix"] = _fetch_vix(idx_q, cfg)

    # ---------- 2. 商品 ----------
    cm_q = _quote_codes([c for c, _ in cfg.COMMODITIES])
    commodities = []
    for code, name in cfg.COMMODITIES:
        f = cm_q.get(code)
        p = _parse_quote(f, "fut") if f else {}
        commodities.append({"name": name, "price": p.get("price"), "chg": p.get("chg")})
    result["commodities"] = commodities

    # ---------- 3. 美股自选股 ----------
    us_codes = [c for c, _, _ in cfg.US_STOCKS]
    us_q = _quote_codes([_realtime_code(c) for c in us_codes])
    us_rows = []
    today = dt.date.today()
    for idx, (code, name, tag) in enumerate(cfg.US_STOCKS):
        f = us_q.get(_realtime_code(code))
        p = _parse_quote(f, "us") if f else {}
        k = _kline_changes(code)
        us_rows.append({
            "code": code.replace("us", "").split(".")[0],
            "name": name, "tag": tag,
            "is_etf": idx >= cfg.US_ETF_START,
            "price": p.get("price"), "chg": p.get("chg"),
            "pe": p.get("pe"), "mcap": p.get("mcap"),
            "chg5": k.get("chg5"), "chg20": k.get("chg20"),
            "chg_ytd": k.get("chg_ytd"),
        })
        if k.get("date"):
            result["us_date"] = k["date"]
    result["us"] = us_rows

    # ---------- 4. 港股自选股 ----------
    hk_codes = [c for c, _, _ in cfg.HK_STOCKS]
    hk_q = _quote_codes(hk_codes)
    extras = _yfinance_extras(cfg)
    hk_rows = []
    for code, name, tag in cfg.HK_STOCKS:
        f = hk_q.get(code)
        p = _parse_quote(f, "hk") if f else {}
        k = _kline_changes(code)
        hk_rows.append({
            "code": code.replace("hk", ""),
            "name": name, "tag": tag,
            "price": p.get("price"), "chg": p.get("chg"),
            "pe": p.get("pe"), "mcap": p.get("mcap"),
            "div": extras["div"].get(code),
            "chg20": k.get("chg20"), "chg_ytd": k.get("chg_ytd"),
        })
        if k.get("date"):
            result["hk_date"] = k["date"]
    result["hk"] = hk_rows

    # ---------- 5. 美债与美元指数（辅助） ----------
    result["treasury"] = extras["treasury"]
    usd = extras.get("usd_index")
    if usd:
        result["commodities"].append({"name": "美元指数", "price": usd, "chg": None})

    # ---------- 6. 板块 / 主题 / 宏观 ETF ----------
    result["etfs"] = _fetch_etfs(cfg)

    result.setdefault("us_date", today.isoformat())
    result.setdefault("hk_date", today.isoformat())
    return result
