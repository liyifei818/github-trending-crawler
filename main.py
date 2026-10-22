"""
GitHub Trending 爬虫 + 数据看板：入口脚本。

用法：
    python main.py                       # 抓每日全语言榜单，生成 index.html
    python main.py -l Python             # 只看 Python
    python main.py -s weekly             # 周榜
    python main.py --demo                # 离线示例数据（不联网，适合预览）
    python main.py --no-open             # 生成后不自动打开浏览器

产物：
    index.html                           可视化看板（可直接双击打开）
    data/trending_<since>_<日期>.csv      当期明细，也是下次运行的历史基线
"""

from __future__ import annotations

import argparse
import datetime
import os
import pathlib
import webbrowser

from analyzer import (
    SINCE_LABELS,
    analyze,
    apply_history,
    find_previous_csv,
    language_breakdown,
    load_snapshot,
    write_csv,
)
from crawler import fetch_trending
from dashboard import render, write_html

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_URL = "https://github.com/liyifei818/github-trending-crawler"

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
    ("redis/redis", "C", 71480, 23910, 74,
     "Redis is an in-memory database that persists on disk."),
    ("grafana/grafana", "TypeScript", 72360, 13420, 61,
     "The open and composable observability and data visualization platform."),
    ("sveltejs/svelte", "JavaScript", 84520, 4620, 132,
     "Cybernetically enhanced web apps"),
]


def build_demo_repos() -> list[dict]:
    """构造 25 条离线示例数据，并伪造少量历史对比字段。"""
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

    # 让界面上的 NEW 徽章与“较上次”增量都有内容可展示
    for index, repo in enumerate(repos):
        if index in (2, 9, 16, 21):
            repo["is_new"] = True
            repo["delta_stars"] = None
        else:
            repo["is_new"] = False
            repo["delta_stars"] = (index * 173) % 980
    return repos


def _print_summary(repos: list[dict], stats: dict, since: str) -> None:
    label = SINCE_LABELS.get(since, since)
    print("\n" + "=" * 56)
    print(f"GitHub Trending · {label}榜单 · 共 {stats['count']} 个仓库")
    print(f"总星标 {stats['total_stars']:,}　周期新增 {stats['total_period_stars']:,}")
    print("-" * 56)

    print("语言分布 Top5：")
    for lang, count in stats["languages"].most_common(5):
        print(f"  {lang:<16} {count}")

    print(f"\n{label}新增星标 Top5：")
    for repo in stats["top_by_period"][:5]:
        print(f"  {repo['full_name']:<34} +{(repo.get('period_stars') or 0):,}")

    new_repos = [r for r in repos if r.get("is_new")]
    if new_repos:
        print(f"\n新上榜 {len(new_repos)} 个：")
        for repo in new_repos[:8]:
            print(f"  + {repo['full_name']}")
    print("=" * 56)


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
        help="CSV 输出目录",
    )
    parser.add_argument("--demo", action="store_true", help="使用离线示例数据")
    parser.add_argument("--no-open", action="store_true", help="生成后不自动打开浏览器")
    args = parser.parse_args()

    today = datetime.date.today().isoformat()
    prev_path: str | None = None
    prev_date: str | None = None

    if args.demo:
        print("使用离线示例数据（不访问网络）…")
        repos = build_demo_repos()
        # 示例数据单独放，避免污染真实的历史快照目录
        outdir = os.path.join(BASE_DIR, "data", "demo")
        html_path = os.path.join(BASE_DIR, "demo.html")
    else:
        outdir = args.outdir
        html_path = os.path.join(BASE_DIR, "index.html")
        print(
            f"正在抓取 GitHub Trending（since={args.since}，"
            f"language={args.language or '全部'}）…"
        )
        repos = fetch_trending(language=args.language, since=args.since)

        prev_path, prev_date = find_previous_csv(outdir, args.since, today)
        previous = load_snapshot(prev_path) if prev_path else None
        apply_history(repos, previous)
        if prev_date:
            print(f"已对比历史快照：{os.path.basename(prev_path)}（{prev_date}）")
        else:
            print("暂无历史快照，本次不做“新上榜 / 增量”对比。")

    stats = analyze(repos)

    csv_path = os.path.join(outdir, f"trending_{args.since}_{today}.csv")
    write_csv(repos, csv_path)

    has_history = bool(prev_date) or args.demo
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
        },
        "stats": {
            "count": stats["count"],
            "total_stars": stats["total_stars"],
            "total_period_stars": stats["total_period_stars"],
            "language_count": stats["language_count"],
            "new_count": stats["new_count"],
            "has_history": has_history,
        },
        "languages": language_breakdown(repos),
        "repos": [
            {
                "rank": r.get("rank"),
                "full_name": r.get("full_name"),
                "language": r.get("language"),
                "stars": r.get("stars"),
                "forks": r.get("forks"),
                "period_stars": r.get("period_stars"),
                "is_new": r.get("is_new"),
                "delta_stars": r.get("delta_stars"),
                "description": r.get("description"),
                "url": r.get("url"),
            }
            for r in repos
        ],
    }

    title = f"GitHub Trending 数据看板 · {today}"
    html = render(payload, title=title, repo_url=REPO_URL)
    write_html(html_path, html)

    _print_summary(repos, stats, args.since)

    if len(repos) < 10:
        print(
            f"\n⚠️  只抓到 {len(repos)} 个仓库（通常为 25 个），"
            "可能被 GitHub 限流。稍等几分钟再试即可。"
        )

    print(f"\n看板已生成：{html_path}")
    print(f"明细已保存：{csv_path}")

    if not args.no_open:
        try:
            webbrowser.open(pathlib.Path(html_path).as_uri())
        except Exception:  # noqa: BLE001  打不开浏览器不影响结果
            pass


if __name__ == "__main__":
    main()
