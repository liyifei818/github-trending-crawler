"""
统计分析：语言分布、增速、历史快照对比、趋势序列，以及 CSV 导出。
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


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def analyze(repos: list[dict]) -> dict:
    """汇总核心指标。"""
    lang_counter = collections.Counter(
        r["language"] for r in repos if r.get("language")
    )
    return {
        "count": len(repos),
        "languages": lang_counter,
        "language_count": len(lang_counter),
        "total_stars": sum(r.get("stars") or 0 for r in repos),
        "total_period_stars": sum(r.get("period_stars") or 0 for r in repos),
        "new_count": sum(1 for r in repos if r.get("is_new")),
        "top_by_stars": sorted(
            repos, key=lambda r: r.get("stars") or 0, reverse=True
        )[:10],
        "top_by_period": sorted(
            repos, key=lambda r: r.get("period_stars") or 0, reverse=True
        )[:10],
        "top_by_growth": sorted(
            repos, key=lambda r: r.get("growth") or 0, reverse=True
        )[:10],
    }


def add_momentum(repos: list[dict]) -> None:
    """计算增速：本期新增星标占现有星标的比例（0~100）。

    单纯按总星标排序，老项目会永远压住新项目；增速能暴露“小体量、
    高热度”的黑马。用现有星标做分母，避免新仓库分母趋近 0 导致数值爆炸。
    """
    for repo in repos:
        stars = repo.get("stars") or 0
        period = repo.get("period_stars") or 0
        repo["growth"] = (
            round(min(period * 100.0 / stars, 100.0), 2) if stars > 0 else None
        )


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


def load_history(
    outdir: str, since: str, today: str, limit: int = 30
) -> list[dict]:
    """读取同一周期的历史快照（日期早于 today），按日期升序返回。

    每个快照形如：
        {"date": "2026-10-22", "repos": {"owner/name": {rank, stars, ...}}}
    """
    if not os.path.isdir(outdir):
        return []

    pattern = os.path.join(outdir, f"trending_{since}_*.csv")
    date_re = re.compile(
        r"trending_%s_(\d{4}-\d{2}-\d{2})\.csv$" % re.escape(since)
    )

    entries: list[tuple[str, str]] = []
    for path in glob.glob(pattern):
        match = date_re.search(os.path.basename(path))
        if not match:
            continue
        date = match.group(1)
        if date >= today:
            continue
        entries.append((date, path))
    entries.sort()

    history: list[dict] = []
    for date, path in entries[-limit:]:
        snapshot: dict[str, dict] = {}
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("full_name") or "").strip()
                if not name:
                    continue
                snapshot[name] = {
                    "rank": _to_int(row.get("rank")),
                    "stars": _to_int(row.get("stars")),
                    "period_stars": _to_int(row.get("period_stars")),
                    "language": (row.get("language") or "").strip() or None,
                }
        history.append({"date": date, "repos": snapshot})
    return history


def build_trend(history: list[dict], repos: list[dict], today: str) -> list[dict]:
    """把历史快照 + 今天，压成画折线图用的序列。"""
    series: list[dict] = []
    for snapshot in history:
        values = list(snapshot["repos"].values())
        count = len(values)
        total = sum(v["stars"] for v in values)
        series.append({
            "date": snapshot["date"],
            "count": count,
            "total_stars": total,
            # 平均星标比总星标更抗名单变动（大仓库进出不会让曲线跳变）
            "avg_stars": round(total / count) if count else 0,
            "total_period_stars": sum(v["period_stars"] for v in values),
        })

    count = len(repos)
    total = sum(r.get("stars") or 0 for r in repos)
    series.append({
        "date": today,
        "count": count,
        "total_stars": total,
        "avg_stars": round(total / count) if count else 0,
        "total_period_stars": sum(r.get("period_stars") or 0 for r in repos),
    })
    return series[-14:]


def apply_history(repos: list[dict], history: list[dict]) -> None:
    """标注：新上榜、星标增量、排名变化、连续在榜天数、累计在榜次数。"""
    previous = history[-1]["repos"] if history else None

    for repo in repos:
        name = repo["full_name"]

        if previous is None:
            repo["is_new"] = None
            repo["delta_stars"] = None
            repo["rank_delta"] = None
            repo["streak"] = None
            repo["appearances"] = None
            continue

        info = previous.get(name)
        if info is None:
            repo["is_new"] = True
            repo["delta_stars"] = None
            repo["rank_delta"] = None
        else:
            repo["is_new"] = False
            current_stars = repo.get("stars")
            repo["delta_stars"] = (
                current_stars - info["stars"]
                if current_stars is not None else None
            )
            repo["rank_delta"] = (
                info["rank"] - repo["rank"]
                if info.get("rank") and repo.get("rank") else None
            )

        # 连续在榜天数（含今天）：从最近一天往回数
        streak = 1
        for snapshot in reversed(history):
            if name in snapshot["repos"]:
                streak += 1
            else:
                break
        repo["streak"] = streak
        repo["appearances"] = 1 + sum(
            1 for snapshot in history if name in snapshot["repos"]
        )


def find_dropped(repos: list[dict], history: list[dict]) -> list[dict]:
    """找出上次在榜、这次消失的仓库。"""
    if not history:
        return []

    previous = history[-1]["repos"]
    current = {r["full_name"] for r in repos}
    dropped = [
        {
            "full_name": name,
            "rank": info.get("rank"),
            "stars": info.get("stars"),
            "language": info.get("language"),
            "url": f"https://github.com/{name}",
        }
        for name, info in previous.items()
        if name not in current
    ]
    dropped.sort(key=lambda item: item.get("rank") or 9999)
    return dropped
