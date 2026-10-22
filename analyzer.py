"""
统计分析：语言分布、星标汇总、历史快照对比，以及 CSV 导出。
仅使用 Python 标准库。
"""

from __future__ import annotations

import collections
import csv
import glob
import os
import re

CSV_FIELDS = [
    "rank", "full_name", "language", "stars", "forks",
    "period_stars", "period", "is_new", "delta_stars",
    "description", "url",
]

SINCE_LABELS = {"daily": "今日", "weekly": "本周", "monthly": "本月"}


def analyze(repos: list[dict]) -> dict:
    """汇总核心指标。"""
    lang_counter = collections.Counter(
        r["language"] for r in repos if r.get("language")
    )
    total_stars = sum(r.get("stars") or 0 for r in repos)
    total_period = sum(r.get("period_stars") or 0 for r in repos)
    return {
        "count": len(repos),
        "languages": lang_counter,
        "language_count": len(lang_counter),
        "total_stars": total_stars,
        "total_period_stars": total_period,
        "new_count": sum(1 for r in repos if r.get("is_new")),
        "top_by_stars": sorted(
            repos, key=lambda r: r.get("stars") or 0, reverse=True
        )[:10],
        "top_by_period": sorted(
            repos, key=lambda r: r.get("period_stars") or 0, reverse=True
        )[:10],
    }


def language_breakdown(repos: list[dict], top_n: int = 8) -> list[dict]:
    """语言分布，超出 top_n 的合并成“其他”，并给出百分比。"""
    # 没有语言标注的也计入，保证环形图各段之和等于仓库总数
    counter = collections.Counter(r.get("language") or "未标注" for r in repos)
    total = sum(counter.values())
    if not total:
        return []

    items = counter.most_common()
    head = items[:top_n]
    rest = sum(count for _, count in items[top_n:])

    result = [
        {"name": name, "count": count, "pct": round(count * 100 / total, 1)}
        for name, count in head
    ]
    if rest:
        result.append(
            {"name": "其他", "count": rest, "pct": round(rest * 100 / total, 1)}
        )
    return result


def write_csv(repos: list[dict], path: str) -> None:
    """按传入顺序（即榜单顺序）写 CSV，rank 保持 GitHub 的真实排名。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for i, r in enumerate(repos, start=1):
            writer.writerow({
                "rank": i,
                "full_name": r.get("full_name") or "",
                "language": r.get("language") or "",
                "stars": r.get("stars") if r.get("stars") is not None else "",
                "forks": r.get("forks") if r.get("forks") is not None else "",
                "period_stars": (
                    r.get("period_stars")
                    if r.get("period_stars") is not None else ""
                ),
                "period": r.get("period") or "",
                "is_new": "" if r.get("is_new") is None else int(bool(r["is_new"])),
                "delta_stars": (
                    r.get("delta_stars")
                    if r.get("delta_stars") is not None else ""
                ),
                "description": r.get("description") or "",
                "url": r.get("url") or "",
            })


def find_previous_csv(
    outdir: str, since: str, today: str
) -> tuple[str | None, str | None]:
    """找同一周期下、日期早于 today 的最近一份 CSV 快照。"""
    if not os.path.isdir(outdir):
        return None, None

    pattern = os.path.join(outdir, f"trending_{since}_*.csv")
    date_re = re.compile(
        r"trending_%s_(\d{4}-\d{2}-\d{2})\.csv$" % re.escape(since)
    )

    best_path, best_date = None, None
    for path in glob.glob(pattern):
        m = date_re.search(os.path.basename(path))
        if not m:
            continue
        date = m.group(1)
        if date >= today:
            continue
        if best_date is None or date > best_date:
            best_path, best_date = path, date
    return best_path, best_date


def load_snapshot(path: str) -> dict[str, int]:
    """读取历史快照，返回 {full_name: stars}。"""
    stars: dict[str, int] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("full_name") or "").strip()
            if not name:
                continue
            try:
                stars[name] = int(row.get("stars") or 0)
            except (TypeError, ValueError):
                stars[name] = 0
    return stars


def apply_history(repos: list[dict], previous: dict[str, int] | None) -> None:
    """标注“新上榜”与“较上次的星标增量”。"""
    for r in repos:
        current = r.get("stars")
        if previous is None:
            r["is_new"] = None
            r["delta_stars"] = None
        elif r["full_name"] not in previous:
            r["is_new"] = True
            r["delta_stars"] = None
        else:
            r["is_new"] = False
            r["delta_stars"] = (
                current - previous[r["full_name"]]
                if current is not None else None
            )
