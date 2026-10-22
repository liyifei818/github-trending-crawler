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
- **深色 / 浅色主题** —— 右上角切换，支持 `?theme=light` 固定主题分享
- **语言分布环形图** —— 按 GitHub linguist 配色，悬停查看占比
- **Top 10 增长榜** —— 可在「周期新增星标」和「总星标」之间切换
- **完整榜单** —— 搜索、语言筛选、只看新上榜、点击表头排序
- **历史快照对比** —— 自动标出「新上榜」，并显示较上次的星标增量
- **导出** —— 一键导出 CSV / 复制 Markdown 表格
- **移动端适配** —— 窄屏自动切换成卡片式布局，无需横向滚动
- **离线示例数据** —— `--demo` 不联网也能预览完整界面
- **单元测试** —— 24 个用例覆盖解析、统计、历史对比与 XSS 转义

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
| `demo.html` | 示例数据看板，不参与真实历史 |
| `data/trending_<周期>_<日期>.csv` | 当期明细，同时作为下次运行的历史基线 |

**历史对比是怎么做的？** 每次运行会找同一周期下、日期早于今天的最近一份 CSV，用它的 `full_name -> stars` 做基线：

- 上次没出现过的仓库 → 标记 **NEW**
- 上次出现过 → 计算「较上次」的星标增量

所以连续运行几天后，看板会自动长出趋势信息。这些 CSV 由 GitHub Actions 自动提交，历史不会丢。

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
├── analyzer.py                  # 统计、语言分布、历史快照对比、CSV
├── dashboard.py                 # HTML 看板模板与渲染
├── main.py                      # 命令行入口
├── index.html                   # 生成的最新看板
├── demo.html                    # 示例数据看板
├── docs/preview.png             # README 预览图
├── data/                        # 每日 CSV 快照（历史基线）
├── docs/update-workflow.yml     # 每日自动更新工作流（一键启用）
└── tests/test_core.py           # 单元测试
```

## 自动更新

仓库附带了现成的工作流文件 [`docs/update-workflow.yml`](docs/update-workflow.yml)，每天 UTC 00:10（北京时间 08:10）自动抓取、重建看板并提交。

启用方式：把它复制到 `.github/workflows/update.yml` 并提交即可，之后也能在 Actions 页面手动触发（Run workflow）。第一次手动触发后，`index.html` 会是完整数据。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 说明与边界

- 仅访问 GitHub 公开页面，不需要登录、不涉及任何私有数据。
- GitHub 对同一 IP 的请求有频率限制，偶尔可能只返回部分条目（程序会提示「只抓到 N 个仓库」），稍等重试即可。
- 页面结构一旦大改，解析可能失效；此时看板仍能生成，但字段可能为空，欢迎提 issue。

## License

[MIT](LICENSE)
