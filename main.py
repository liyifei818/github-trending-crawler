"""
GitHub Trending 爬虫：入口脚本。
用法：
    python main.py                      # 抓取每日全语言榜单
    python main.py -l Python            # 只看 Python
    python main.py -l Python -s weekly  # Python 周榜
结果：
    - data/trending_<日期>.csv        仓库明细
    - data/lang_dist.svg              语言分布图
    - data/top_stars.svg              星标 Top10 图
"""

from __future__ import annotations

import argparse
import datetime
import os

from crawler import fetch_trending
from analyzer import analyze, write_csv, make_bar_svg


def _print_summary(repos, stats, since):
    print("\n" + "=" * 48)
    print(f"GitHub Trending（{since}）共抓取 {stats['count']} 个仓库")
    print(f"总星标：{stats['total_stars']:,}　"
          f"周期新增星标：{stats['total_period_stars']:,}")
    print("-" * 48)
    print("语言分布 Top5：")
    for lang, cnt in stats["languages"].most_common(5):
        print(f"  {lang:<14} {cnt}")
    print("星标最高的 5 个仓库：")
    for r in stats["top_by_stars"][:5]:
        print(f"  {r['full_name']:<32} 星星{(r.get('stars') or 0):,}  "
              f"({r.get('language') or '—'})")
    print("=" * 48)


def main():
    parser = argparse.ArgumentParser(
        description="抓取并分析 GitHub Trending 热门仓库（零依赖）"
    )
    parser.add_argument("-l", "--language", help="按语言筛选，如 Python / JavaScript")
    parser.add_argument(
        "-s", "--since", default="daily",
        choices=["daily", "weekly", "monthly"],
        help="时间范围，默认 daily",
    )
    parser.add_argument("-o", "--outdir", default="data", help="输出目录")
    args = parser.parse_args()

    print(f"正在抓取 GitHub Trending（since={args.since}，"
          f"language={args.language or '全部'}）...")
    repos = fetch_trending(language=args.language, since=args.since)
    stats = analyze(repos)

    date = datetime.date.today().isoformat()
    os.makedirs(args.outdir, exist_ok=True)
    csv_path = os.path.join(args.outdir, f"trending_{date}.csv")
    write_csv(repos, csv_path)

    lang_items = stats["languages"].most_common(10)
    make_bar_svg(lang_items, "GitHub Trending 语言分布 Top10",
                 os.path.join(args.outdir, "lang_dist.svg"))
    top_items = [(r["full_name"], r["stars"] or 0)
                 for r in stats["top_by_stars"]]
    make_bar_svg(top_items, "星标最高的 10 个仓库",
                 os.path.join(args.outdir, "top_stars.svg"))

    _print_summary(repos, stats, args.since)
    print(f"\n明细已保存：{csv_path}")
    print(f"图表已保存：{os.path.join(args.outdir, 'lang_dist.svg')} "
          f"与 {os.path.join(args.outdir, 'top_stars.svg')}")


if __name__ == "__main__":
    main()
