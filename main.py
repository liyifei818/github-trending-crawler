"""
GitHub Trending 爬虫 + 数据看板：入口脚本。

用法：
    python main.py                       # 抓每日全语言榜单，生成 index.html
    python main.py -l Python             # 只看 Python
    python main.py -s weekly             # 周榜
    python main.py --demo                # 离线示例数据（不联网，适合预览）
    python main.py --no-open             # 生成后不自动打开浏览器

产物：
    index.html                            可视化看板（可直接双击打开）
    feed.xml                              RSS 订阅源
    data/trending_<since>_<日期>.csv       当期明细，也是下次运行的历史基线
    data/latest_<since>.json              机器可读的当期快照
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import webbrowser

from analyzer import (
    SINCE_LABELS,
    add_momentum,
    analyze,
    apply_history,
    build_trend,
    find_dropped,
    language_breakdown,
    load_history,
    write_csv,
)
from crawler import fetch_trending
from dashboard import render, write_html
from feed import build_rss

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_URL = "https://github.com/liyifei818/github-trending-crawler"
SITE_URL = "https://liyifei818.github.io/github-trending-crawler/"

# 离线示例数据：(仓库, 语言, 总星标, Fork, 周期新增, 描述)
_DEMO_ROWS = [
    ("Graphify-Labs/graphify", "Python", 132493, 12695, 1407,
     "Turn any codebase, with its docs, SQL schemas, configs, and PDFs, into a queryable knowledge graph."),
    ("fastapi/fastapi", "Python", 103521, 10076, 96,
     "FastAPI framework, high performance, easy to learn, fast to code, ready for production"),
    ("php/php-src", "C", 40913, 8286, 110, "The PHP Interpreter"),
    ("torvalds/linux", "C", 218402, 63150, 312, "Linux kernel source tree"),
    ("microsoft/vscode", "TypeScript", 182340, 37120, 245,
     "Visual Studio Code — code editing. Redefined."),
    ("facebook/react", "JavaScript", 243180, 50210, 188,
     "The library for web and native user interfaces."),
    ("vercel/next.js", "JavaScript", 139560, 30240, 210, "The React Framework"),
    ("rust-lang/rust", "Rust", 112870, 14890, 274,
     "Empowering everyone to build reliable and efficient software."),
    ("golang/go", "Go", 132460, 19430, 156, "The Go programming language"),
    ("ollama/ollama", "Go", 168940, 14210, 892,
     "Get up and running with large language models."),
    ("langchain-ai/langchain", "Python", 121340, 19870, 341,
     "Build context-aware reasoning applications"),
    ("huggingface/transformers", "Python", 152780, 31260, 402,
     "State-of-the-art machine learning for PyTorch, TensorFlow, and JAX."),
    ("pytorch/pytorch", "Python", 95740, 26180, 233,
     "Tensors and dynamic neural networks in Python with strong GPU acceleration"),
    ("tensorflow/tensorflow", "C++", 193420, 74820, 97,
     "An Open Source Machine Learning Framework for Everyone"),
    ("astral-sh/uv", "Rust", 68230, 2010, 521,
     "An extremely fast Python package and project manager, written in Rust."),
    ("denoland/deno", "Rust", 104920, 5830, 143,
     "A modern runtime for JavaScript and TypeScript."),
    ("tauri-apps/tauri", "Rust", 92180, 2810, 189,
     "Build smaller, faster, and more secure desktop applications with a web frontend."),
    ("microsoft/playwright", "TypeScript", 78140, 4520, 167,
     "A framework for Web Testing and Automation."),
    ("shadcn-ui/ui", "TypeScript", 93210, 6410, 305,
     "Beautifully designed components you can copy and paste into your apps."),
    ("supabase/supabase", "TypeScript", 88470, 9210, 128,
     "The open source Firebase alternative."),
    ("n8n-io/n8n", "TypeScript", 152340, 43280, 612,
     "Fair-code workflow automation platform with native AI capabilities."),
    ("kubernetes/kubernetes", "Go", 118930, 41020, 88,
     "Production-Grade Container Scheduling and Management"),
    ("karpathy/nanochat", "Python", 4120, 380, 980,
     "The best ChatGPT that $100 can buy."),
    ("grafana/grafana", "TypeScript", 72360, 13420, 61,
     "The open and composable observability and data visualization platform."),
    ("openbmb/MiniCPM", "Python", 8960, 1240, 610,
     "A family of small language models that run on device."),
]


def build_demo_repos() -> list[dict]:
    """构造 25 条离线示例数据。"""
    repos: list[dict] = []
    for index, row in enumerate(_DEMO_ROWS, start=1):
        full_name, language, stars, forks, period_stars, description = row
        owner, name = full_name.split("/", 1)
        repos.append({
            "rank": index,
            "full_name": full_name,
            "owner": owner,
            "name": name,
            "url": f"https://github.com/{full_name}",
            "description": description,
            "language": language,
            "stars": stars,
            "forks": forks,
            "period_stars": period_stars,
            "period": "today",
        })
    return repos


def build_demo_history(repos: list[dict], days: int = 12) -> list[dict]:
    """伪造 12 天历史，让趋势图、连续在榜、掉榜在示例页里都能看到。"""
    history: list[dict] = []
    today = datetime.date.today()
    for offset in range(days, 0, -1):
        day = (today - datetime.timedelta(days=offset)).isoformat()
        snapshot: dict[str, dict] = {}
        for index, repo in enumerate(repos):
            # 每隔几天让个别仓库缺席，制造“新上榜”和“掉榜”
            if (index * 3 + offset) % 11 == 0:
                continue
            current = repo.get("stars") or 0
            period = repo.get("period_stars") or 0
            decay = min(period * offset * 0.85, current * 0.35)
            snapshot[repo["full_name"]] = {
                "rank": ((index + offset) % len(repos)) + 1,
                "stars": max(int(current - decay), 0),
                "period_stars": max(int(period * (1 - 0.02 * offset)), 0),
                "language": repo.get("language"),
            }
        # 两个“只存在于历史里”的仓库，用来展示掉榜面板
        snapshot["vinta/awesome-python"] = {
            "rank": 22,
            "stars": 224000 - offset * 90,
            "period_stars": 28,
            "language": "Python",
        }
        snapshot["jwasham/coding-interview-university"] = {
            "rank": 25,
            "stars": 316000 - offset * 70,
            "period_stars": 19,
            "language": "Markdown",
        }
        history.append({"date": day, "repos": snapshot})
    return history


def _print_summary(
    repos: list[dict], stats: dict, since: str, dropped: list[dict]
) -> None:
    label = SINCE_LABELS.get(since, since)
    print("\n" + "=" * 58)
    print(f"GitHub Trending · {label}榜单 · 共 {stats['count']} 个仓库")
    print(f"总星标 {stats['total_stars']:,}　周期新增 {stats['total_period_stars']:,}")
    print("-" * 58)

    print("语言分布 Top5：")
    for lang, count in stats["languages"].most_common(5):
        print(f"  {lang:<18} {count}")

    print(f"\n{label}新增星标 Top5：")
    for repo in stats["top_by_period"][:5]:
        print(f"  {repo['full_name']:<36} +{(repo.get('period_stars') or 0):,}")

    print("\n增速 Top5（本期新增 / 现有星标）：")
    for repo in stats["top_by_growth"][:5]:
        print(f"  {repo['full_name']:<36} {(repo.get('growth') or 0):>6.2f}%")

    new_repos = [r for r in repos if r.get("is_new")]
    if new_repos:
        print(f"\n新上榜 {len(new_repos)} 个：")
        for repo in new_repos[:6]:
            print(f"  + {repo['full_name']}")

    if dropped:
        print(f"\n掉榜 {len(dropped)} 个：")
        for item in dropped[:6]:
            print(f"  - {item['full_name']}")
    print("=" * 58)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="抓取 GitHub Trending 并生成可视化数据看板（零依赖）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-l", "--language", help="按语言筛选，如 Python / Rust")
    parser.add_argument(
        "-s", "--since", default="daily",
        choices=["daily", "weekly", "monthly"], help="时间范围",
    )
    parser.add_argument(
        "-o", "--outdir", default=os.path.join(BASE_DIR, "data"),
        help="CSV / JSON 输出目录",
    )
    parser.add_argument("--demo", action="store_true", help="使用离线示例数据")
    parser.add_argument("--no-open", action="store_true", help="生成后不自动打开浏览器")
    args = parser.parse_args()

    today = datetime.date.today().isoformat()

    if args.demo:
        print("使用离线示例数据（不访问网络）…")
        repos = build_demo_repos()
        history = build_demo_history(repos)
        outdir = os.path.join(BASE_DIR, "data", "demo")
        html_path = os.path.join(BASE_DIR, "demo.html")
        rss_path = os.path.join(BASE_DIR, "demo.xml")
    else:
        outdir = args.outdir
        html_path = os.path.join(BASE_DIR, "index.html")
        rss_path = os.path.join(BASE_DIR, "feed.xml")
        print(
            f"正在抓取 GitHub Trending（since={args.since}，"
            f"language={args.language or '全部'}）…"
        )
        repos = fetch_trending(language=args.language, since=args.since)
        history = load_history(outdir, args.since, today)

    apply_history(repos, history)
    add_momentum(repos)
    stats = analyze(repos)
    dropped = find_dropped(repos, history)
    trend = build_trend(history, repos, today)

    prev_date = history[-1]["date"] if history else None
    if prev_date:
        print(f"已对比历史快照：{prev_date}（共 {len(history)} 天）")
    else:
        print("暂无历史快照，本次不做“新上榜 / 增量 / 掉榜”对比。")

    csv_path = os.path.join(outdir, f"trending_{args.since}_{today}.csv")
    write_csv(repos, csv_path)

    label = SINCE_LABELS.get(args.since, args.since)
    payload = {
        "meta": {
            "date": today,
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "since": args.since,
            "since_label": label,
            "period_label": label + "热门",
            "language": args.language,
            "prev_date": prev_date,
            "demo": bool(args.demo),
            "site_url": SITE_URL,
        },
        "stats": {
            "count": stats["count"],
            "total_stars": stats["total_stars"],
            "total_period_stars": stats["total_period_stars"],
            "language_count": stats["language_count"],
            "new_count": stats["new_count"],
            "has_history": bool(history),
        },
        "languages": language_breakdown(repos),
        "history": trend,
        "dropped": dropped,
        "repos": [
            {
                "rank": r.get("rank"),
                "full_name": r.get("full_name"),
                "language": r.get("language"),
                "stars": r.get("stars"),
                "forks": r.get("forks"),
                "period_stars": r.get("period_stars"),
                "growth": r.get("growth"),
                "is_new": r.get("is_new"),
                "delta_stars": r.get("delta_stars"),
                "rank_delta": r.get("rank_delta"),
                "streak": r.get("streak"),
                "appearances": r.get("appearances"),
                "description": r.get("description"),
                "url": r.get("url"),
            }
            for r in repos
        ],
    }

    title = f"GitHub Trending 数据看板 · {today}"
    html = render(payload, title=title, repo_url=REPO_URL)
    write_html(html_path, html)

    json_path = os.path.join(outdir, f"latest_{args.since}.json")
    os.makedirs(outdir, exist_ok=True)
    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(rss_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(build_rss(repos, payload["meta"], SITE_URL))

    _print_summary(repos, stats, args.since, dropped)

    if len(repos) < 5:
        print(
            f"\n注意：本次只解析到 {len(repos)} 个仓库。GitHub 有时会返回精简榜单，"
            "也可能触发了限流；稍后重试即可。"
        )

    print(f"\n看板已生成：{html_path}")
    print(f"CSV 明细：{csv_path}")
    print(f"JSON 快照：{json_path}")
    print(f"RSS 订阅：{rss_path}")

    if not args.no_open:
        try:
            webbrowser.open(pathlib.Path(html_path).as_uri())
        except Exception:  # noqa: BLE001  打不开浏览器不影响结果
            pass


if __name__ == "__main__":
    main()
