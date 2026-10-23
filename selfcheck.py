"""
项目自检：一条命令跑完「测试 + 产物 + 渲染 + 线上」四层检查。

用法：
    python selfcheck.py                 # 本地：单元测试 + 产物校验 + 浏览器渲染检查
    python selfcheck.py --online        # 额外检查线上部署（GitHub Pages）
    python selfcheck.py --github        # 额外检查 GitHub Actions 最近一次运行
    python selfcheck.py --skip-browser  # 跳过浏览器检查（无浏览器环境）

任何一项失败都会以非零退出码结束，方便挂到 CI 上做守门。

零第三方依赖：只用 Python 标准库。浏览器检查是可选的，检测不到浏览器就跳过。
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_URL = "https://liyifei818.github.io/github-trending-crawler/"
GITHUB_REPO = "liyifei818/github-trending-crawler"

# 页面必须包含的关键结构（缺一个就说明模板被改坏了）
REQUIRED_MARKERS = [
    'id="trend"',
    'id="droppedPanel"',
    'data-key="growth"',
    'type="application/rss+xml"',
    'id="trend-data"',
]


class Check:
    """一条检查结果。"""

    def __init__(self, name: str, ok: bool, detail: str = "", skipped: bool = False):
        self.name = name
        self.ok = ok
        self.detail = detail
        self.skipped = skipped

    def line(self) -> str:
        if self.skipped:
            mark = "SKIP"
        elif self.ok:
            mark = " OK "
        else:
            mark = "FAIL"
        text = f"[{mark}] {self.name}"
        if self.detail:
            text += f" — {self.detail}"
        return text


RESULTS: list[Check] = []


def record(name: str, ok: bool, detail: str = "", skipped: bool = False) -> Check:
    check = Check(name, ok, detail, skipped)
    RESULTS.append(check)
    return check


# ---------------------------------------------------------------- 1. 单元测试

def check_unit_tests() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=BASE_DIR, capture_output=True, text=True,
    )
    tail = (proc.stderr or proc.stdout).strip().splitlines()
    summary = tail[-1] if tail else "无输出"
    if proc.returncode != 0:
        record("单元测试", False, summary)
        for line in tail[-15:]:
            print("      " + line)
    else:
        record("单元测试", True, summary)


# ---------------------------------------------------------------- 2. 产物一致性

def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _page_data(html: str) -> dict:
    match = re.search(r'id="trend-data"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise ValueError("页面里找不到 trend-data 数据块")
    return json.loads(match.group(1))


def check_artifacts() -> None:
    index_path = os.path.join(BASE_DIR, "index.html")
    demo_path = os.path.join(BASE_DIR, "demo.html")
    json_path = os.path.join(BASE_DIR, "data", "latest_daily.json")
    feed_path = os.path.join(BASE_DIR, "feed.xml")

    missing = [p for p in (index_path, demo_path, json_path, feed_path)
               if not os.path.exists(p)]
    if missing:
        record("产物齐全", False,
               "缺少 " + ", ".join(os.path.basename(p) for p in missing))
        return
    record("产物齐全", True, "index.html / demo.html / feed.xml / latest_daily.json")

    # 2.1 页面结构
    problems = []
    for name, path in (("index.html", index_path), ("demo.html", demo_path)):
        html = _read(path)
        for marker in REQUIRED_MARKERS:
            if marker not in html:
                problems.append(f"{name} 缺少 {marker}")
        if re.search(r"__(DATA|TITLE|REPO_URL)__", html):
            problems.append(f"{name} 残留未替换的模板占位符")
    record("页面结构完整", not problems, "；".join(problems) if problems else
           "所有关键节点与占位符正常")

    # 2.2 JSON 与页面同源
    html_data = _page_data(_read(index_path))
    json_data = json.loads(_read(json_path))
    same = (
        html_data["meta"]["date"] == json_data["meta"]["date"]
        and html_data["meta"]["generated_at"] == json_data["meta"]["generated_at"]
        and len(html_data["repos"]) == len(json_data["repos"])
        and all(
            a["full_name"] == b["full_name"] and a["stars"] == b["stars"]
            for a, b in zip(html_data["repos"], json_data["repos"])
        )
    )
    record("HTML 与 JSON 同源", same,
           f"{html_data['meta']['date']} / {len(html_data['repos'])} 个仓库")

    # 2.3 RSS 合法且顺序与榜单一致
    try:
        channel = ET.parse(feed_path).getroot().find("channel")
        items = channel.findall("item")
        titles = [i.findtext("title") for i in items]
        expected = [
            r["full_name"] for r in sorted(
                html_data["repos"],
                key=lambda x: (x.get("period_stars") or 0, x.get("stars") or 0),
                reverse=True,
            )
        ][:10]
        ok = titles == expected[:len(titles)]
        record("RSS 合法且与榜单同序", ok,
               f"{len(items)} 条" if ok else f"顺序不符：{titles[:3]}")
    except Exception as e:  # noqa: BLE001
        record("RSS 合法且与榜单同序", False, f"解析失败：{e}")


# ---------------------------------------------------------------- 3. 浏览器渲染

BROWSER_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]

# 注入页面的探针：真实点击表头、输入搜索，然后把结果写进 DOM
PROBE_JS = r"""
<script>
window.addEventListener("load", function () {
  var out = { rows: 0, sorts: {}, search: {}, errors: [] };
  var COL = { rank: 0, stars: 3, period_stars: 4, growth: 5, forks: 6, delta_stars: 7 };
  function num(t) {
    var m = String(t).replace(/,/g, "").match(/-?\d+(\.\d+)?/);
    return m ? parseFloat(m[0]) : null;
  }
  function colValues(key) {
    var idx = COL[key];
    return Array.prototype.map.call(
      document.querySelectorAll("#tbody tr"),
      function (tr) { return num(tr.children[idx] && tr.children[idx].textContent); }
    ).filter(function (v) { return v !== null; });
  }
  try {
    out.rows = document.querySelectorAll("#tbody tr").length;
    ["rank", "stars", "period_stars", "growth", "forks", "delta_stars"].forEach(
      function (key) {
        var th = document.querySelector('th[data-key="' + key + '"]');
        if (!th) return;
        th.click();
        var dir = th.getAttribute("aria-sort");
        var vals = colValues(key);
        var mono = true;
        for (var i = 1; i < vals.length; i++) {
          if (dir === "descending" ? vals[i] > vals[i - 1] : vals[i] < vals[i - 1]) {
            mono = false; break;
          }
        }
        out.sorts[key] = {
          dir: dir, n: vals.length, mono: mono,
          first: vals.length ? vals[0] : null,
          last: vals.length ? vals[vals.length - 1] : null
        };
      }
    );
    // 排序后复位到榜单顺序
    var rankTh = document.querySelector('th[data-key="rank"]');
    if (rankTh) rankTh.click();
    // 搜索过滤
    var s = document.getElementById("search");
    var total = out.rows;
    s.value = "a"; s.dispatchEvent(new Event("input", { bubbles: true }));
    var filtered = document.querySelectorAll("#tbody tr").length;
    s.value = ""; s.dispatchEvent(new Event("input", { bubbles: true }));
    out.search = { total: total, filtered: filtered,
                   restored: document.querySelectorAll("#tbody tr").length };
  } catch (e) {
    out.errors.push(String(e && e.message || e));
  }
  var d = document.createElement("div");
  d.id = "selfcheck-probe";
  d.textContent = JSON.stringify(out);
  document.body.appendChild(d);
});
</script>
</body>"""


def find_browser() -> str | None:
    for path in BROWSER_PATHS:
        if os.path.exists(path):
            return path
    for name in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def check_browser(skip: bool = False) -> None:
    index_path = os.path.join(BASE_DIR, "index.html")
    if not os.path.exists(index_path):
        record("浏览器渲染检查", False, "缺少 index.html，先跑 python main.py")
        return

    browser = None if skip else find_browser()
    if not browser:
        record("浏览器渲染检查", True, "未找到浏览器，已跳过", skipped=True)
        return

    html = _read(index_path)
    with tempfile.TemporaryDirectory() as tmp:
        probe_file = os.path.join(tmp, "probe.html")
        with open(probe_file, "w", encoding="utf-8") as f:
            f.write(html.replace("</body>", PROBE_JS, 1))
        profile = os.path.join(tmp, "profile")
        file_url = pathlib.Path(probe_file).as_uri()
        try:
            proc = subprocess.run(
                [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
                 "--user-data-dir=" + profile, "--virtual-time-budget=6000",
                 "--dump-dom", file_url],
                capture_output=True, text=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            record("浏览器渲染检查", False, "浏览器渲染超时")
            return

    dom = proc.stdout or ""
    match = re.search(r'id="selfcheck-probe"[^>]*>(.*?)</div>', dom, re.S)
    if not match:
        record("浏览器渲染检查", False, "探针未执行，页面可能存在 JS 错误")
        return
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        record("浏览器渲染检查", False, "探针输出无法解析")
        return

    problems = list(data.get("errors") or [])
    expected_rows = len(_page_data(html)["repos"])
    if data.get("rows") != expected_rows:
        problems.append(
            f"表格行数 {data.get('rows')} ≠ 数据条数 {expected_rows}"
        )

    # 排序方向必须与 aria-sort 一致且单调
    for key, info in (data.get("sorts") or {}).items():
        if not info.get("mono"):
            problems.append(
                f"{key} 排序与 aria-sort={info.get('dir')} 不一致"
                f"（首 {info.get('first')} 末 {info.get('last')}）"
            )

    search = data.get("search") or {}
    if search.get("total") and search.get("filtered") >= search.get("total"):
        problems.append("搜索没有真正过滤掉行")
    if search.get("restored") != search.get("total"):
        problems.append("清空搜索后行数没有复原")

    record("浏览器渲染检查", not problems,
           "；".join(problems) if problems else
           f"{data.get('rows')} 行渲染正常，6 个排序方向一致，搜索/复原正常")


# ---------------------------------------------------------------- 4. 线上 / Actions

def _fetch(url: str, timeout: int = 25) -> tuple[int, str]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "selfcheck/1.0", "Cache-Control": "no-cache"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:  # noqa: BLE001
        return -1, ""


def check_online() -> None:
    status, html = _fetch(SITE_URL)
    if status != 200:
        record("线上首页可访问", False, f"HTTP {status}")
        return
    try:
        html_data = _page_data(html)
    except ValueError as e:
        record("线上首页可访问", False, f"数据块异常：{e}")
        return
    record("线上首页可访问", True,
           f"HTTP 200 / {html_data['meta']['date']} / "
           f"{len(html_data['repos'])} 个仓库")

    for label, path in (("线上 RSS", "feed.xml"),
                        ("线上 JSON", "data/latest_daily.json")):
        st, body = _fetch(SITE_URL + path)
        ok = st == 200 and len(body) > 100
        record(label, ok, f"HTTP {st} / {len(body)} bytes")

    # 线上 HTML 与线上 JSON 是否同源
    st, body = _fetch(SITE_URL + "data/latest_daily.json")
    if st == 200:
        try:
            json_data = json.loads(body)
            same = (
                json_data["meta"]["date"] == html_data["meta"]["date"]
                and len(json_data["repos"]) == len(html_data["repos"])
            )
            record("线上 HTML 与 JSON 同源", same,
                   f"{json_data['meta']['date']} / {len(json_data['repos'])} 个仓库")
        except Exception as e:  # noqa: BLE001
            record("线上 HTML 与 JSON 同源", False, str(e))


def check_actions() -> None:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        record("GitHub Actions 最近运行", True,
               "未设置 GITHUB_TOKEN，已跳过", skipped=True)
        return
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/update.yml/runs?per_page=1"
    request = urllib.request.Request(url)
    request.add_header("Authorization", "Bearer " + token)
    request.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(request, timeout=25) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:  # noqa: BLE001
        record("GitHub Actions 最近运行", False, f"查询失败：{e}")
        return
    runs = data.get("workflow_runs") or []
    if not runs:
        record("GitHub Actions 最近运行", False, "没有任何运行记录")
        return
    run = runs[0]
    ok = run.get("status") == "completed" and run.get("conclusion") == "success"
    record("GitHub Actions 最近运行", ok,
           f"#{run.get('run_number')} {run.get('status')}/"
           f"{run.get('conclusion')} 事件={run.get('event')} "
           f"于 {run.get('created_at')}")


# ---------------------------------------------------------------- 入口

def main() -> int:
    parser = argparse.ArgumentParser(
        description="GitHub Trending 爬虫项目自检",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--online", action="store_true", help="额外检查线上部署")
    parser.add_argument("--github", action="store_true", help="额外检查 GitHub Actions")
    parser.add_argument("--skip-browser", action="store_true", help="跳过浏览器检查")
    args = parser.parse_args()

    print("=" * 62)
    print("GitHub Trending 爬虫 · 自检")
    print("=" * 62)

    check_unit_tests()
    check_artifacts()
    check_browser(skip=args.skip_browser)
    if args.online:
        check_online()
    if args.github:
        check_actions()

    print("-" * 62)
    for check in RESULTS:
        print(check.line())
    failed = [c for c in RESULTS if not c.ok]
    skipped = [c for c in RESULTS if c.skipped]
    print("-" * 62)
    if failed:
        print(f"自检未通过：{len(failed)} 项失败，{len(skipped)} 项跳过")
        return 1
    print(f"自检通过：{len(RESULTS) - len(skipped)} 项通过"
          + (f"，{len(skipped)} 项跳过" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
