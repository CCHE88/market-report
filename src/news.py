# -*- coding: utf-8 -*-
"""
新闻获取模块 —— 让 LLM 知道"今天发生了什么"

这是云端方案保持 AI 深度分析质量的关键：LLM 本身不具备实时信息，
必须把当日新闻注入 prompt，否则只能输出空泛套话。

数据源：Yahoo Finance RSS（免费、无需 API key、国内境外均可访问）
  按标的分组抓取，天然覆盖宏观指数 / 美股科技 / 黄金能源 / 港股四个维度。

可选增强：配置 TAVILY_API_KEY 后会自动追加一轮 Tavily 深度搜索
  （需付费额度，免费版每日限额较低）。
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbols}&region=US&lang=en-US"

# 按标的分组抓新闻：既覆盖宏观，也覆盖每只自选股的相关动态
GROUPS = [
    ("宏观市场", "^DJI,^IXIC,^GSPC,^VIX,^TNX"),
    ("美股科技", "NVDA,TSM,AMD,AVGO,MU,SNDK,MRVL,MSFT,GOOGL,AMZN,META,TSLA"),
    ("黄金能源", "GLD,NEM,XOM,CVX,GC=F,CL=F"),
    ("港股中概", "0700.HK,9988.HK,3690.HK,0005.HK,0941.HK,0883.HK,2318.HK,2899.HK"),
]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _fetch_rss(symbols: str, limit: int = 8) -> list[dict]:
    """抓取一组标的的 RSS 头条"""
    url = RSS_URL.format(symbols=urllib.parse.quote(symbols))
    try:
        req = urllib.request.Request(url, headers=UA, method="GET")
        with urllib.request.urlopen(req, timeout=25) as resp:
            xml = resp.read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"[news] RSS 抓取失败: {str(e)[:60]}")
        return []

    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S)[:limit]:
        def grab(tag):
            m = re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", block, re.S)
            return (m.group(1).strip() if m else "")

        title = grab("title")
        if not title:
            continue
        desc = re.sub(r"<[^>]+>", "", grab("description"))[:280]
        items.append({
            "title": title,
            "content": desc,
            "url": grab("link"),
            "date": grab("pubDate"),
        })
    return items


def _tavily_extra(query: str, limit: int = 4) -> list[dict]:
    """可选的 Tavily 深度搜索（需配置 TAVILY_API_KEY 且有额度）"""
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        path = os.path.expanduser("~/.workbuddy/skills/tavily-search__skillhub/config.json")
        try:
            with open(path, encoding="utf-8") as f:
                key = json.load(f).get("api_key")
        except Exception:
            key = None
    if not key:
        return []
    payload = {"api_key": key, "query": query, "search_depth": "basic",
               "max_results": limit, "topic": "news"}
    try:
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [{"title": r.get("title", ""),
                 "content": (r.get("content") or "")[:280],
                 "url": r.get("url", ""), "date": ""}
                for r in data.get("results", [])]
    except Exception:
        return []   # Tavily 不可用时静默降级，不影响主流程


def fetch_all(limit_per_group: int = 8) -> dict[str, list[dict]]:
    """抓取全部新闻，返回 {分组: [新闻]}"""
    result = {}
    for tag, symbols in GROUPS:
        items = _fetch_rss(symbols, limit=limit_per_group)
        result[tag] = items
        print(f"[news] {tag}: {len(items)} 条")

    extra = _tavily_extra("US stock market today Federal Reserve inflation")
    if extra:
        result["深度搜索"] = extra
        print(f"[news] 深度搜索(Tavily): {len(extra)} 条")
    return result


def to_prompt_text(news: dict[str, list[dict]], max_chars: int = 7000) -> str:
    """压缩为可注入 prompt 的文本（控制 token 预算）"""
    lines, total = [], 0
    for tag, items in news.items():
        if not items:
            continue
        lines.append(f"\n【{tag}】")
        for it in items:
            chunk = f"- {it['title']}"
            if it["content"]:
                chunk += f" — {it['content'][:200]}"
            if total + len(chunk) > max_chars:
                break
            lines.append(chunk)
            total += len(chunk)
    return "\n".join(lines)


if __name__ == "__main__":
    n = fetch_all()
    print("\n" + "=" * 64)
    print(to_prompt_text(n)[:2500])
