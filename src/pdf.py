# -*- coding: utf-8 -*-
"""
PDF 转换模块 —— 基于 Playwright (Chromium)

在 GitHub Actions 上需先执行: playwright install --with-deps chromium
未安装时自动跳过，不影响 HTML 生成与推送。
"""

from __future__ import annotations

from pathlib import Path


def html_to_pdf(html_path: str, pdf_path: str) -> bool:
    """把 HTML 渲染为 A4 PDF。成功返回 True。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[pdf] 未安装 playwright，跳过 PDF 生成（仅输出 HTML）")
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = browser.new_page()
            page.goto(Path(html_path).resolve().as_uri(), wait_until="networkidle")
            page.emulate_media(media="print")
            page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                margin={"top": "8mm", "bottom": "8mm", "left": "8mm", "right": "8mm"},
            )
            browser.close()
        ok = Path(pdf_path).exists()
        if ok:
            size = Path(pdf_path).stat().st_size / 1024 / 1024
            print(f"[pdf] PDF 生成成功: {pdf_path} ({size:.2f} MB)")
        return ok
    except Exception as e:
        print(f"[pdf] PDF 转换失败: {e}")
        return False
