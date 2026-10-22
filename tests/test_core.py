"""核心逻辑单元测试：python -m unittest discover -s tests -v"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

# 让测试可以直接 import 项目根目录下的模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer import (  # noqa: E402
    analyze,
    apply_history,
    find_previous_csv,
    language_breakdown,
    load_snapshot,
    write_csv,
)
from crawler import build_url, parse_trending  # noqa: E402
from dashboard import render  # noqa: E402

# 尽量贴近 GitHub Trending 真实结构的夹具
FIXTURE = """
<div class="Box">
<article class="Box-row Box-row--focus-gray">
  <h2 class="h3 lh-condensed">
    <a href="/Graphify-Labs/graphify" class="Link">Graphify-Labs / graphify</a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">
    Turn any codebase &amp; docs into a <code>queryable</code> graph.
  </p>
  <span itemprop="programmingLanguage">Python</span>
  <a href="/Graphify-Labs/graphify/stargazers">
    <svg><path d="M8 0C3.58 0 0 3.58 0 8"/></svg> 132,493
  </a>
  <a href="/Graphify-Labs/graphify/forks">
    <svg><path d="M5 3.25a2.25 2.25"/></svg> 12,695
  </a>
  <span class="d-inline-block float-sm-right"><svg></svg> 1,407 stars today</span>
</article>

<article class="Box-row">
  <h2 class="h3 lh-condensed"><a href="/redis/redis">redis</a></h2>
  <p class="col-9">In-memory &lt;database&gt; that persists</p>
  <span itemprop="programmingLanguage">C</span>
  <a href="/redis/redis/stargazers"><svg></svg> 71,480</a>
  <a href="/redis/redis/forks"><svg></svg> 23,910</a>
  <span><svg></svg> 74 stars this week</span>
</article>

<article class="Box-row">
  <a href="/sponsors/someone">Sponsor</a>
</article>
</div>
"""


class TestBuildUrl(unittest.TestCase):
    def test_default(self):
        self.assertEqual(build_url(), "https://github.com/trending")

    def test_language(self):
        self.assertEqual(
            build_url("Python"), "https://github.com/trending/python"
        )

    def test_language_with_space(self):
        self.assertEqual(
            build_url("Jupyter Notebook"),
            "https://github.com/trending/jupyter-notebook",
        )

    def test_plus_sign_must_not_be_encoded(self):
        # GitHub 的路径就是 /trending/c++，编码成 c%2B%2B 会 404
        self.assertEqual(build_url("C++"), "https://github.com/trending/c++")

    def test_sharp_sign_is_encoded(self):
        self.assertEqual(build_url("C#"), "https://github.com/trending/c%23")

    def test_since(self):
        self.assertEqual(
            build_url(None, "weekly"),
            "https://github.com/trending?since=weekly",
        )


class TestParseTrending(unittest.TestCase):
    def setUp(self):
        self.repos = parse_trending(FIXTURE)

    def test_skips_non_repo_articles(self):
        self.assertEqual(len(self.repos), 2)

    def test_basic_fields(self):
        repo = self.repos[0]
        self.assertEqual(repo["full_name"], "Graphify-Labs/graphify")
        self.assertEqual(repo["language"], "Python")
        self.assertEqual(repo["stars"], 132493)
        self.assertEqual(repo["forks"], 12695)
        self.assertEqual(repo["period_stars"], 1407)
        self.assertEqual(repo["period"], "today")
        self.assertEqual(repo["rank"], 1)
        self.assertEqual(repo["url"], "https://github.com/Graphify-Labs/graphify")

    def test_description_unescaped(self):
        self.assertEqual(
            self.repos[0]["description"],
            "Turn any codebase & docs into a queryable graph.",
        )
        self.assertEqual(
            self.repos[1]["description"], "In-memory <database> that persists"
        )

    def test_stars_not_from_svg_path(self):
        # 如果没先剥掉标签，可能会把 path 里的 3.58 / 0 当成星标
        self.assertNotIn(self.repos[0]["stars"], (358, 0, 8))
        self.assertEqual(self.repos[1]["stars"], 71480)

    def test_weekly_period(self):
        self.assertEqual(self.repos[1]["period"], "this week")
        self.assertEqual(self.repos[1]["period_stars"], 74)

    def test_ranks_are_sequential(self):
        self.assertEqual([r["rank"] for r in self.repos], [1, 2])


class TestAnalyze(unittest.TestCase):
    def setUp(self):
        self.repos = [
            {"full_name": "a/1", "language": "Python", "stars": 100, "period_stars": 10},
            {"full_name": "b/2", "language": "Python", "stars": 50, "period_stars": 5},
            {"full_name": "c/3", "language": "Go", "stars": 20, "period_stars": 0},
            {"full_name": "d/4", "language": None, "stars": 5, "period_stars": None},
        ]

    def test_totals(self):
        stats = analyze(self.repos)
        self.assertEqual(stats["count"], 4)
        self.assertEqual(stats["total_stars"], 175)
        self.assertEqual(stats["total_period_stars"], 15)
        self.assertEqual(stats["language_count"], 2)

    def test_language_breakdown(self):
        result = language_breakdown(self.repos)
        self.assertEqual(result[0]["name"], "Python")
        self.assertEqual(result[0]["count"], 2)
        # 无语言标注的归入“未标注”，各段之和等于仓库总数
        self.assertEqual(sum(item["count"] for item in result), 4)
        self.assertAlmostEqual(result[0]["pct"], 50.0, places=1)
        names = [item["name"] for item in result]
        self.assertIn("未标注", names)

    def test_language_breakdown_groups_rest(self):
        repos = [
            {"language": "A"}, {"language": "A"},
            {"language": "B"}, {"language": "C"},
        ]
        result = language_breakdown(repos, top_n=1)
        self.assertEqual(result[0]["name"], "A")
        self.assertEqual(result[0]["count"], 2)
        self.assertEqual(result[-1]["name"], "其他")
        self.assertEqual(result[-1]["count"], 2)

    def test_empty(self):
        stats = analyze([])
        self.assertEqual(stats["count"], 0)
        self.assertEqual(stats["total_stars"], 0)
        self.assertEqual(language_breakdown([]), [])


class TestHistory(unittest.TestCase):
    def test_new_and_delta(self):
        repos = [
            {"full_name": "a/1", "stars": 100},
            {"full_name": "b/2", "stars": 50},
        ]
        apply_history(repos, {"a/1": 80})
        self.assertFalse(repos[0]["is_new"])
        self.assertEqual(repos[0]["delta_stars"], 20)
        self.assertTrue(repos[1]["is_new"])
        self.assertIsNone(repos[1]["delta_stars"])

    def test_no_history(self):
        repos = [{"full_name": "a/1", "stars": 100}]
        apply_history(repos, None)
        self.assertIsNone(repos[0]["is_new"])
        self.assertIsNone(repos[0]["delta_stars"])

    def test_find_previous_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            def make(name, stars):
                write_csv(
                    [{"full_name": "a/1", "stars": stars}],
                    os.path.join(tmp, name),
                )

            make("trending_daily_2026-01-01.csv", 10)
            make("trending_daily_2026-01-02.csv", 20)
            make("trending_weekly_2026-01-02.csv", 99)

            path, date = find_previous_csv(tmp, "daily", "2026-01-03")
            self.assertEqual(date, "2026-01-02")
            self.assertTrue(path.endswith("trending_daily_2026-01-02.csv"))

            snapshot = load_snapshot(path)
            self.assertEqual(snapshot, {"a/1": 20})

    def test_ignores_today_and_future(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_csv(
                [{"full_name": "a/1", "stars": 10}],
                os.path.join(tmp, "trending_daily_2026-01-03.csv"),
            )
            path, date = find_previous_csv(tmp, "daily", "2026-01-03")
            self.assertIsNone(path)
            self.assertIsNone(date)

    def test_missing_dir(self):
        path, date = find_previous_csv("no/such/dir", "daily", "2026-01-03")
        self.assertIsNone(path)
        self.assertIsNone(date)


class TestRender(unittest.TestCase):
    def _payload(self, description):
        return {
            "meta": {"date": "2026-01-01"},
            "stats": {},
            "languages": [],
            "repos": [{"full_name": "x/y", "description": description}],
        }

    def test_escapes_script_breakout(self):
        html = render(
            self._payload("</script><img src=x onerror=alert(1)>"),
            "T", "https://github.com/u/r",
        )
        self.assertNotIn("</script><img", html)
        self.assertNotIn("<img", html)
        self.assertIn("\\u003c/script", html)

    def test_placeholders_replaced(self):
        html = render(self._payload("ok"), "标题", "https://github.com/u/r")
        self.assertNotIn("__DATA__", html)
        self.assertNotIn("__TITLE__", html)
        self.assertNotIn("__REPO_URL__", html)
        self.assertIn("标题", html)

    def test_empty_data_renders(self):
        html = render(
            {"meta": {}, "stats": {}, "languages": [], "repos": []},
            "E", "https://github.com/u/r",
        )
        self.assertIn('id="trend-data"', html)
        self.assertIn('id="tbody"', html)


if __name__ == "__main__":
    unittest.main()
