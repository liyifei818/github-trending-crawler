"""
GitHub Trending 爬虫（零依赖，仅用 Python 标准库）

功能：抓取 https://github.com/trending 当日的热门仓库，
解析出仓库名、语言、总星标、Fork 数、周期新增星标、描述等信息。
"""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request

TRENDING_URL = "https://github.com/trending"

# 加一个常见浏览器的 User-Agent，避免被 GitHub 直接拒绝
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _slug(language: str) -> str:
    """把语言名转成 GitHub Trending 的 URL slug。"""
    s = language.strip().lower()
    s = s.replace(" ", "-")
    s = urllib.parse.quote(s, safe="-+#")
    return s


def build_url(language: str | None, since: str) -> str:
    if language:
        url = f"{TRENDING_URL}/{_slug(language)}"
    else:
        url = TRENDING_URL
    # 带语言筛选时，必须带 since 参数（GitHub 规则）
    url += f"?since={urllib.parse.quote(since)}" if language else (
        f"?since={urllib.parse.quote(since)}" if since != "daily" else ""
    )
    return url


def fetch_html(url: str, retries: int = 2) -> str:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"无法抓取 {url}: {last_err}")


def _parse_int(text: str | None):
    if not text:
        return None
    text = text.strip().replace(",", "")
    if not text.isdigit():
        return None
    return int(text)


def _extract_repo(block: str) -> dict | None:
    # 仓库路径：第一个 /owner/repo（恰好两段）
    m = re.search(r'href="/([^"/?#]+)/([^"/?#]+)"', block)
    if not m:
        return None
    owner, name = m.group(1), m.group(2)
    # 过滤掉像 /sponsors/xxx 这类非仓库链接
    if owner in ("sponsors", "login", "new", "about"):
        return None
    full_name = f"{owner}/{name}"

    # 描述：class 含 col-9 的 <p>
    dm = re.search(r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', block, re.S)
    description = re.sub(r"<[^>]+>", "", dm.group(1)).strip() if dm else ""

    # 语言
    lm = re.search(r'itemprop="programmingLanguage">([^<]+)</span>', block)
    language = lm.group(1).strip() if lm else None

    # 总星标（stargazers 链接内、图标 svg 之后的数字）
    sm = re.search(r'/stargazers"[^>]*>.*?</svg>\s*([\d,]+)\s*</a>', block, re.S)
    stars = _parse_int(sm.group(1)) if sm else None

    # Fork 数
    fm = re.search(r'/forks"[^>]*>.*?</svg>\s*([\d,]+)\s*</a>', block, re.S)
    forks = _parse_int(fm.group(1)) if fm else None

    # 时间段内新增星标
    pm = re.search(r'([\d,]+)\s+stars\s+(today|this week|this month)', block)
    period_stars = _parse_int(pm.group(1)) if pm else None
    period = pm.group(2) if pm else None

    return {
        "full_name": full_name,
        "owner": owner,
        "name": name,
        "url": f"https://github.com/{full_name}",
        "description": description,
        "language": language,
        "stars": stars,
        "forks": forks,
        "period_stars": period_stars,
        "period": period,
    }


def parse_trending(html: str) -> list[dict]:
    repos: list[dict] = []
    parts = html.split('<article class="Box-row">')
    for part in parts[1:]:
        block = part.split("</article>")[0]
        repo = _extract_repo(block)
        if repo:
            repos.append(repo)
    return repos


def fetch_trending(language: str | None = None, since: str = "daily") -> list[dict]:
    """抓取 GitHub Trending 并返回仓库字典列表。"""
    url = build_url(language, since)
    html = fetch_html(url)
    repos = parse_trending(html)
    if not repos:
        raise ValueError(
            "没有解析到任何仓库，GitHub 可能改版或请求被拦截。"
            "可稍后重试，或检查网络/User-Agent。"
        )
    return repos
