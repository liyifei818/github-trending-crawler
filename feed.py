"""生成 RSS 2.0 订阅源（零依赖，仅用标准库）。"""

from __future__ import annotations

import datetime
from email.utils import format_datetime
from xml.sax.saxutils import escape


def build_rss(repos: list[dict], meta: dict, site_url: str, limit: int = 10) -> str:
    """把当期榜单写成 RSS，默认只放周期新增最高的 10 个仓库。"""
    since_label = meta.get("since_label") or "今日"
    now = datetime.datetime.now(datetime.timezone.utc)

    ordered = sorted(
        repos,
        key=lambda r: (r.get("period_stars") or 0, r.get("stars") or 0),
        reverse=True,
    )[:limit]

    items: list[str] = []
    for repo in ordered:
        name = repo.get("full_name") or ""
        url = repo.get("url") or ""
        description = repo.get("description") or ""
        prefix = ""
        if repo.get("period_stars") is not None:
            prefix += f"+{repo['period_stars']:,} stars {since_label} · "
        if repo.get("language"):
            prefix += f"{repo['language']} · "
        items.append(
            "    <item>\n"
            f"      <title>{escape(name)}</title>\n"
            f"      <link>{escape(url)}</link>\n"
            f"      <guid isPermaLink='true'>{escape(url)}</guid>\n"
            f"      <description>{escape(prefix + description)}</description>\n"
            f"      <pubDate>{format_datetime(now)}</pubDate>\n"
            "    </item>"
        )

    title = f"GitHub Trending · {since_label}榜单"
    self_url = site_url.rstrip("/") + "/feed.xml"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{escape(title)}</title>\n"
        f"    <link>{escape(site_url)}</link>\n"
        f"    <description>{escape('每天更新的 GitHub 热门仓库榜单')}</description>\n"
        "    <language>zh-cn</language>\n"
        f"    <lastBuildDate>{format_datetime(now)}</lastBuildDate>\n"
        f"    <atom:link href='{escape(self_url)}' rel='self' type='application/rss+xml'/>\n"
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )
