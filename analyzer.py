"""
对抓取到的 GitHub Trending 仓库做统计分析，并生成 CSV 与 SVG 柱状图。
仅使用 Python 标准库。
"""

from __future__ import annotations

import collections
import csv
import os


def analyze(repos: list[dict]) -> dict:
    lang_counter = collections.Counter(
        r["language"] for r in repos if r.get("language")
    )
    total_stars = sum(r.get("stars") or 0 for r in repos)
    total_period = sum(r.get("period_stars") or 0 for r in repos)
    by_stars = sorted(repos, key=lambda r: r.get("stars") or 0, reverse=True)
    by_period = sorted(repos, key=lambda r: r.get("period_stars") or 0, reverse=True)
    return {
        "count": len(repos),
        "languages": lang_counter,
        "total_stars": total_stars,
        "total_period_stars": total_period,
        "top_by_stars": by_stars[:10],
        "top_by_period": by_period[:10],
    }


def write_csv(repos: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fields = [
        "rank", "full_name", "language", "stars", "forks",
        "period_stars", "period", "description", "url",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i, r in enumerate(sorted(
            repos, key=lambda x: x.get("stars") or 0, reverse=True
        ), start=1):
            writer.writerow({
                "rank": i,
                "full_name": r.get("full_name"),
                "language": r.get("language") or "",
                "stars": r.get("stars") or "",
                "forks": r.get("forks") or "",
                "period_stars": r.get("period_stars") or "",
                "period": r.get("period") or "",
                "description": r.get("description") or "",
                "url": r.get("url") or "",
            })


def make_bar_svg(items: list[tuple], title: str, path: str, width: int = 760) -> None:
    """items: list of (label, value)，生成水平柱状图 SVG。"""
    if not items:
        return
    label_w = 170
    bar_area = width - label_w - 70
    row_h = 32
    height = 44 + len(items) * row_h
    max_val = max((v for _, v in items), default=1) or 1

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" font-family="Segoe UI, Arial, sans-serif">',
        f'<text x="16" y="26" font-size="17" font-weight="bold" fill="#1f2328">{title}</text>',
    ]
    for i, (label, val) in enumerate(items):
        y = 44 + i * row_h
        bar_len = max(int(bar_area * (val / max_val)), 2)
        parts.append(
            f'<text x="4" y="{y + 18}" font-size="12" fill="#1f2328">'
            f'{_escape(str(label))}</text>'
        )
        parts.append(
            f'<rect x="{label_w}" y="{y + 4}" width="{bar_len}" height="20" '
            f'rx="3" fill="#2f81f7"/>'
        )
        parts.append(
            f'<text x="{label_w + bar_len + 6}" y="{y + 19}" '
            f'font-size="12" fill="#57606a">{val:,}</text>'
        )
    parts.append("</svg>")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
