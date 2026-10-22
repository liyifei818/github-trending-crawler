"""
GitHub Trending 爬虫（零依赖，仅用 Python 标准库）。

GitHub 没有公开的 Trending API，所以这里直接解析 HTML 页面。页面结构随时
可能变，因此解析逻辑写得尽量宽容：
  - 不写死 <article> 的完整 class 属性，只要求包含 Box-row；
  - 星标 / Fork 不依赖图标位置，而是取对应链接内的第一段数字；
  - 描述做 HTML 反转义，避免出现 &amp; &quot; 之类的残留。
"""

from __future__ import annotations

import html as html_lib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

TRENDING_URL = "https://github.com/trending"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# 每个仓库被 <article class="Box-row"> 包裹。GitHub 偶尔会追加其它 class，
# 所以按“class 里含有 Box-row”来匹配，比精确匹配整个属性更稳。
ARTICLE_RE = re.compile(
    r'<article\b[^>]*class="[^"]*\bBox-row\b[^"]*"[^>]*>(.*?)</article>',
    re.S,
)

# 仓库标题：<h2 class="h3 lh-condensed"><a href="/owner/repo">
TITLE_LINK_RE = re.compile(
    r'<h2\b[^>]*class="[^"]*\blh-condensed\b[^"]*"[^>]*>\s*'
    r'<a\b[^>]*href="/([^"/?#]+)/([^"/?#]+)"',
    re.S,
)

ANY_LINK_RE = re.compile(r'href="/([^"/?#]+)/([^"/?#]+)"')

# 这些一级路径不是仓库，匹配到需要跳过
RESERVED = {
    "sponsors", "login", "join", "new", "about", "topics", "collections",
    "trending", "settings", "features", "enterprise", "marketplace",
    "pricing", "explore", "notifications", "orgs", "users", "site",
    "security", "contact", "codespaces", "mobile", "search", "dashboard",
    "issues", "pulls", "apps", "account", "organizations", "readme",
}

REPO_PART_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# 形如 “1,407 stars today” / “96 stars this week”
PERIOD_RE = re.compile(
    r"([\d,]+)\s+stars?\s+(today|this\s+week|this\s+month)", re.I
)


def _slug(language: str) -> str:
    """把语言名转成 Trending 路径片段（C++ -> c++，C# -> c%23）。"""
    s = language.strip().lower().replace(" ", "-")
    # '+' 在 GitHub 路径里是合法字符，不能转义；'#' 必须转义
    return urllib.parse.quote(s, safe="+-")


def build_url(language: str | None = None, since: str = "daily") -> str:
    """拼接 Trending 地址。daily 是默认值，可以省略 since 参数。"""
    url = f"{TRENDING_URL}/{_slug(language)}" if language else TRENDING_URL
    if since and since != "daily":
        url += "?" + urllib.parse.urlencode({"since": since})
    return url


def fetch_html(url: str, retries: int = 3) -> str:
    """带重试的 GET。403/429 说明被限流，退避更久一点。"""
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (403, 429):
                time.sleep(5 * (attempt + 1))
            elif attempt < retries:
                time.sleep(1.5 * (attempt + 1))
        except Exception as e:  # noqa: BLE001  网络类异常统一重试
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"无法抓取 {url}：{last_err}")


def _parse_int(text: str | None) -> int | None:
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


def _clean_text(fragment: str) -> str:
    """去标签 -> 反转义 HTML 实体 -> 压缩空白。"""
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _anchor_number(block: str, href_part: str) -> int | None:
    """取某个链接（如 /stargazers）内部的第一段数字。"""
    pattern = r'href="[^"]*%s[^"]*"[^>]*>(.*?)</a>' % re.escape(href_part)
    m = re.search(pattern, block, re.S)
    if not m:
        return None
    # 链接内部有 <svg><path d="..."></path></svg>，先把标签剔除再找数字，
    # 否则可能把 path 的坐标当成星标数。
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    num = re.search(r"\d[\d,]*", text)
    return _parse_int(num.group(0)) if num else None


def _find_repo_name(block: str) -> tuple[str, str] | None:
    m = TITLE_LINK_RE.search(block)
    if m:
        return m.group(1), m.group(2)
    # 兜底：扫所有 /owner/repo 形式的链接，跳过保留路径
    for cand in ANY_LINK_RE.finditer(block):
        if cand.group(1).lower() not in RESERVED:
            return cand.group(1), cand.group(2)
    return None


def _extract_repo(block: str) -> dict | None:
    found = _find_repo_name(block)
    if not found:
        return None
    owner, name = found
    if (
        owner.lower() in RESERVED
        or not REPO_PART_RE.match(owner)
        or not REPO_PART_RE.match(name)
    ):
        return None

    full_name = f"{owner}/{name}"

    dm = re.search(
        r'<p\b[^>]*class="[^"]*\bcol-9\b[^"]*"[^>]*>(.*?)</p>', block, re.S
    )
    description = _clean_text(dm.group(1)) if dm else ""

    lm = re.search(
        r'itemprop="programmingLanguage"[^>]*>(.*?)</span>', block, re.S
    )
    language = _clean_text(lm.group(1)) if lm else None

    stars = _anchor_number(block, "stargazers")
    forks = _anchor_number(block, "/forks")

    # 周期新增星标：在去掉标签后的纯文本里找，避免 svg 干扰
    plain = _clean_text(block)
    pm = PERIOD_RE.search(plain)
    period_stars = _parse_int(pm.group(1)) if pm else None
    period = re.sub(r"\s+", " ", pm.group(2)).lower() if pm else None

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
    """解析 Trending 页面，返回按页面顺序（即榜单排名）排列的仓库列表。"""
    repos: list[dict] = []
    seen: set[str] = set()
    for block in ARTICLE_RE.findall(html):
        repo = _extract_repo(block)
        if not repo or repo["full_name"] in seen:
            continue
        seen.add(repo["full_name"])
        repo["rank"] = len(repos) + 1
        repos.append(repo)
    return repos


def fetch_trending(
    language: str | None = None, since: str = "daily"
) -> list[dict]:
    """抓取 GitHub Trending 并返回仓库字典列表。"""
    url = build_url(language, since)
    html = fetch_html(url)
    repos = parse_trending(html)
    if not repos:
        raise ValueError(
            "没有解析到任何仓库：GitHub 可能改版、限流或网络异常。"
            "可以稍后重试，或用 python main.py --demo 先看离线示例。"
        )
    return repos
