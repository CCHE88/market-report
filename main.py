# -*- coding: utf-8 -*-
"""
每日市场晨报 —— 云端独立版主入口

不依赖 WorkBuddy 桌面客户端，可在 GitHub Actions / 任意服务器上定时运行。

用法:
    python main.py                  # 完整流程（数据 → HTML → PDF → 推送）
    python main.py --no-pdf         # 跳过 PDF 转换
    python main.py --no-push        # 跳过微信推送
    python main.py --dry-run        # 只生成 HTML，不做后续
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import config as cfg                              # noqa: E402
from src import analyzer, builder, fetcher, notifier        # noqa: E402
from src.pdf import html_to_pdf                             # noqa: E402

OUT_DIR = ROOT / "output"
WEEKDAY = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-pdf", action="store_true", help="跳过 PDF 转换")
    ap.add_argument("--no-push", action="store_true", help="跳过微信推送")
    ap.add_argument("--dry-run", action="store_true", help="只生成 HTML")
    args = ap.parse_args()

    today = dt.date.today()
    stamp = today.isoformat()
    date_label = f"{stamp}（{WEEKDAY[today.weekday()]}）"
    print(f"==> 生成 {date_label} 市场晨报")

    # 1. 拉取行情
    print("    [1/5] 拉取行情数据 ...")
    data = fetcher.fetch_all(cfg)

    # 2. 生成买卖建议
    print("    [2/5] 生成买卖建议 ...")
    for r in data.get("us", []):
        r["advice"], r["logic"] = analyzer.rule_advice(r, "us")
        r["advice_style"] = analyzer.ADVICE_STYLE.get(r["advice"], "advice-hold")
    for r in data.get("hk", []):
        r["advice"], r["logic"] = analyzer.rule_advice(r, "hk")
        r["advice_style"] = analyzer.ADVICE_STYLE.get(r["advice"], "advice-hold")

    # 3. 生成分析文案
    print("    [3/5] 生成分析文案 ...")
    nar = analyzer.build_narrative(data)
    print(f"          文案来源: {nar.get('source')} "
          f"({'AI 生成' if nar.get('source') == 'llm' else '规则模板'})")

    # 4. 生成 HTML
    print("    [4/5] 生成 HTML ...")
    meta = {
        "date_label": date_label,
        "us_date": data.get("us_date", stamp),
        "hk_date": data.get("hk_date", stamp),
        "css": _read("assets/report.css"),
        "logo_b64": _read("assets/logo.txt"),
        "title": cfg.REPORT_TITLE,
        "company": cfg.COMPANY,
        "disclaimer": cfg.DISCLAIMER,
        "cfg": cfg,
    }
    html = builder.build_html(data, nar, meta)
    OUT_DIR.mkdir(exist_ok=True)
    html_path = OUT_DIR / f"market-report-{stamp}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"          HTML 已生成: {html_path}")

    if args.dry_run:
        print("==> dry-run 模式，流程结束")
        return

    # 5. 转换 PDF
    pdf_path = OUT_DIR / f"market-report-{stamp}.pdf"
    has_pdf = False
    if not args.no_pdf:
        print("    [5/5] 转换 PDF ...")
        has_pdf = html_to_pdf(str(html_path), str(pdf_path))

    # 6. 微信推送
    if not args.no_push:
        base = os.getenv("REPORT_BASE_URL", "").rstrip("/")
        pdf_url = f"{base}/market-report-{stamp}.pdf" if (base and has_pdf) else None
        html_url = f"{base}/market-report-{stamp}.html" if base else None
        content = notifier.build_content(data, nar, date_label, pdf_url, html_url)
        title = f"市场晨报 {today.month}月{today.day}日｜美港股+美元债"
        ok = notifier.send(title, content)
        print(f"          微信推送: {'成功（服务端已受理）' if ok else '失败或跳过'}")
        if not base:
            print("          提示: 未配置 REPORT_BASE_URL，推送消息不含链接")

    print("==> 完成")


if __name__ == "__main__":
    main()
