# GitHub Trending 数据看板

**零依赖**的 GitHub Trending 爬虫 + 可视化看板。抓取每日 / 每周 / 每月的热门仓库，生成一个**单文件 HTML** 看板——双击就能看，断网也能看。

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

**在线预览：** https://liyifei818.github.io/github-trending-crawler/

![看板预览](docs/preview.png)

---

## 特性

- **零第三方依赖** —— 只用 Python 标准库，不用装 requests / bs4 / matplotlib
- **单文件看板** —— 数据内联进 HTML，不依赖 CDN，离线可用
- **历史趋势曲线** —— 把每天的快照连成线，可切换「周期新增 / 平均星标 / 收录数」
- **增速维度** —— 本期新增星标 ÷ 现有星标，专门暴露「小体量、高热度」的黑马，不被老仓库的大星标压住
- **排名变化与在榜天数** —— 较上次上升/下降几位、连续在榜多少天、累计上榜几次
- **掉榜清单** —— 上次在榜、本次消失的仓库单独列出
- **深色 / 浅色主题** —— 右上角切换，支持 `?theme=light` 固定主题分享
- **语言分布环形图** —— 按 GitHub linguist 配色，悬停查看占比
- **Top 10 榜单** —— 可在「周期新增 / 增速 / 总星标」之间切换
- **完整榜单** —— 搜索、语言筛选、只看新上榜、点击表头排序
- **可分享的筛选** —— 筛选条件写进 URL（`?q=` `?lang=` `?sort=`），发链接即可复现
- **导出与订阅** —— 一键导出 CSV、复制 Markdown，另出 JSON 快照与 RSS
- **移动端适配** —— 窄屏自动切换成卡片式布局，无需横向滚动
- **离线示例数据** —— `--demo` 不联网也能预览完整界面
- **单元测试** —— 33 个用例覆盖解析、统计、历史、增速、RSS 与 XSS 转义

## 快速开始

```bash
git clone https://github.com/liyifei818/github-trending-crawler.git
cd github-trending-crawler

python main.py
```

运行结束会自动打开生成的 `index.html`。

> 只想看界面效果、不想联网？运行 `python main.py --demo`，会生成 `demo.html`。

### 命令行参数

| 参数 | 简写 | 说明 |
| --- | --- | --- |
| `--language` | `-l` | 按语言筛选，如 `Python`、`Rust`、`C++` |
| `--since` | `-s` | 时间范围：`daily` / `weekly` / `monthly`，默认 `daily` |
| `--outdir` | `-o` | CSV 输出目录，默认 `data/` |
| `--demo` | | 使用离线示例数据，生成 `demo.html` |
| `--no-open` | | 生成后不自动打开浏览器（适合 CI） |

示例：

```bash
python main.py -l Python            # 只看 Python 的今日榜
python main.py -s weekly            # 本周榜
python main.py -l Rust -s monthly   # Rust 月榜
```

## 输出说明

| 文件 | 内容 |
| --- | --- |
| `index.html` | 最新看板（自动更新，也是 GitHub Pages 的入口） |
| `feed.xml` | RSS 2.0 订阅源（当期新增最高的 10 个仓库） |
| `demo.html` / `demo.xml` | 示例数据看板与订阅源，不参与真实历史 |
| `data/trending_<周期>_<日期>.csv` | 当期明细，同时作为下次运行的历史基线 |
| `data/latest_<周期>.json` | 机器可读的完整快照（`meta / stats / history / dropped / repos`） |

**历史对比是怎么做的？** 每次运行会读取同一周期、日期早于今天的全部 CSV（最多 30 天），然后：

- 上次没出现过的仓库 → 标记 **NEW**
- 上次出现过 → 计算「较上次」的星标增量，以及排名上升/下降几位
- 从最近一天往回数连续在榜天数，并统计累计上榜次数
- 上次在榜、本次消失的仓库 → 进入「掉出榜单」
- 所有快照的汇总值 → 画成历史趋势曲线

所以连续运行几天后，看板会自动长出趋势、排名变化和掉榜信息。

## 数据接口

除了给人看的 HTML，每次运行还会产出机器可读的数据：

- **JSON**：`data/latest_<周期>.json`，包含 `meta`、`stats`、`languages`、`history`、`dropped`、`repos`
- **RSS**：`feed.xml`，取当期新增星标最高的 10 个仓库

部署到 GitHub Pages 后可直接访问：

```
https://liyifei818.github.io/github-trending-crawler/data/latest_daily.json
https://liyifei818.github.io/github-trending-crawler/feed.xml
```

## 工作原理

GitHub 没有公开的 Trending API，所以项目直接解析 `https://github.com/trending` 的 HTML。为了抗改版，解析层做了这些事：

- 不写死 `<article>` 的完整 class，只要求包含 `Box-row`
- 星标 / Fork 取对应链接内的第一段数字，并先剔掉 `<svg>` 里的路径数据
- 描述做 HTML 反转义，避免残留 `&amp;` / `&quot;`
- 语言名转 URL 时保留 `+`（`C++` 必须是 `/trending/c++`，编码成 `%2B%2B` 会 404）
- 请求失败自动重试，遇到 403/429 退避更久

## 项目结构

```
.
├── crawler.py                   # 抓取 + 解析 Trending HTML
├── analyzer.py                  # 统计、增速、历史对比、趋势序列、CSV
├── dashboard.py                 # HTML 看板模板与渲染
├── feed.py                      # RSS 2.0 生成
├── main.py                      # 命令行入口
├── index.html                   # 生成的最新看板
├── feed.xml                     # 生成的 RSS 订阅源
├── demo.html / demo.xml         # 示例数据产物
├── docs/preview.png             # README 预览图
├── data/                        # CSV 历史快照 + JSON 快照
├── .github/workflows/update.yml # 每日自动更新
└── tests/test_core.py           # 单元测试
```

## 自动更新

`.github/workflows/update.yml` 每天 UTC 00:10（北京时间 08:10）自动抓取、重建看板与订阅源并提交，也可以在 Actions 页面手动触发（Run workflow）。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 说明与边界

- 仅访问 GitHub 公开页面，不需要登录、不涉及任何私有数据。
- GitHub 返回的榜单条数并不固定：实测同一时刻 daily 可能只有 9 条、weekly 15 条、monthly 20 条，这不代表抓取失败。少于 5 条时程序才会提示异常。
- 页面结构一旦大改，解析可能失效；此时看板仍能生成，但字段可能为空，欢迎提 issue。

## License

[MIT](LICENSE)
