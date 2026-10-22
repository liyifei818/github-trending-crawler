# GitHub Trending 爬虫 🔥

一个**零依赖**的 GitHub 热门仓库爬虫与分析工具。用纯 Python 标准库抓取
[GitHub Trending](https://github.com/trending)，解析出仓库的语言、星标、Fork、
周期新增星标等数据，并生成 CSV 明细 + SVG 可视化图表。

> 研究目标：搞清楚「GitHub 上现在什么技术正在变火」。数据来自 GitHub 官方 Trending 页面。
> 源码地址：<https://github.com/liyifei818/github-trending-crawler>

## ✨ 功能

- 🕷️ 抓取每日 / 每周 / 每月 Trending 榜单
- 🔍 支持按语言筛选（Python、JavaScript、Rust…）
- 📊 统计语言分布、总星标、Top 仓库
- 🖼️ 自动生成语言分布图与星标 Top10 柱状图（SVG）
- 📄 导出 CSV 明细，方便二次分析
- 📦 **零第三方依赖**，clone 下来 `python main.py` 就能跑

## 🚀 快速开始

无需安装任何依赖，Python 3.8+ 即可：

```bash
# 抓取每日全语言榜单
python main.py

# 只看 Python 的每日榜单
python main.py -l Python

# Python 周榜
python main.py -l Python -s weekly
```

运行后会在 `data/` 目录生成：

| 文件 | 说明 |
|------|------|
| `trending_<日期>.csv` | 仓库明细（星标、Fork、语言、描述等） |
| `lang_dist.svg` | 语言分布 Top10 柱状图 |
| `top_stars.svg` | 星标最高的 10 个仓库 |

## 📁 项目结构

```
github-trending-crawler/
├── crawler.py        # 抓取 + 解析 GitHub Trending 页面
├── analyzer.py       # 统计分析 + 生成 CSV / SVG 图表
├── main.py           # 命令行入口
├── requirements.txt  # 依赖说明（本项目为零依赖）
├── .gitignore
└── data/             # 运行生成的结果（已忽略，不纳入版本库）
```

## 🛠️ 实现说明

- 抓取：`urllib.request` 带浏览器 UA 请求 Trending 页面
- 解析：用正则从 HTML 中提取仓库信息（无 BeautifulSoup 依赖）
- 图表：手写轻量 SVG（无需 matplotlib）
- 数据来源：<https://github.com/trending>

## 📌 注意事项

- GitHub Trending 没有官方 API，本工具解析其网页，**页面改版时可能需要同步更新解析逻辑**。
- 请勿高频请求，避免触发限流。建议加入缓存或降低频率，便于长期跟踪研究。

## 📄 License

MIT
