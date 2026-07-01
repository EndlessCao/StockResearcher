# Stock Research Agent

Stock Research Agent 是一款本地优先的 AI 研报工具，可根据研究问题和参考资料生成结构化 Markdown 研报，并支持围绕研报进行连续问答。

项目提供原生 macOS App、命令行工具和 HTTP API。

## 主要功能

- 根据研究主题自动生成完整研报。
- 支持 `quick`、`standard`、`deep` 三种研究深度。
- 支持导入本地文件、文件夹和网页链接。
- 支持 Tavily、Brave、SerpAPI 网络搜索。
- 支持 PDF、Markdown、TXT、CSV 和 JSON 文件。
- 支持证券代码、数据截止日期和资料类型筛选。
- 研报包含目录、核心判断、事实依据、风险、反方观点、参考来源和免责声明。
- 来源引用可以在 Markdown 中点击跳转。
- 支持研报列表、重命名、置顶和删除。
- 支持基于研报的多轮问答，对话历史会自动保存。
- 支持后台生成、进度查看和任务取消。
- 支持独立 macOS App，最终用户不需要安装 Python 或 `uv`。

## 使用 macOS App

### 系统要求

- Apple Silicon Mac
- macOS 14 或更高版本

### 安装

1. 打开 `StockResearcher-macOS.dmg`。
2. 将 `StockResearcher.app` 拖入“Applications”目录。
3. 打开应用。
4. 进入“设置 → 模型与数据”，填写模型和搜索服务配置。

首次运行时，应用会在用户目录下创建：

```text
~/.stock_researcher/
```

应用配置、研报、任务和对话记录均保存在该目录中。

### 生成研报

1. 点击“新建研报”。
2. 输入研究问题。
3. 选择研究深度。
4. 按需添加本地文件、文件夹或网页链接。
5. 按需填写证券代码和数据截止日期。
6. 选择是否启用网络搜索。
7. 提交任务，在生成队列中查看进度。

任务完成后，可以在研报列表中阅读、重命名、置顶、删除或继续提问。

## 使用命令行

### 环境要求

- Python 3.10 或更高版本
- `uv`

安装依赖：

```bash
uv sync
```

在项目根目录创建 `.env`，至少配置一个兼容 OpenAI API 的模型：

```dotenv
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://your-api-endpoint/v1
OPENAI_MODEL=your_model
```

### 生成研报

```bash
uv run research-agent report \
  --topic "分析英伟达未来三年的增长潜力" \
  --mode standard \
  --stock-code NVDA \
  --data-cutoff 2026-06-30 \
  --output ./reports
```

`--output` 接收目录地址。研报文件会使用研报标题命名，例如：

```text
./reports/英伟达 AI 芯片业务深度研报.md
```

### 使用本地资料

```bash
uv run research-agent report \
  --topic "分析某公司的竞争优势与主要风险" \
  --sources ./materials \
  --no-web \
  --output ./reports
```

`--sources` 可以重复使用，同时添加文件、文件夹或 URL：

```bash
uv run research-agent report \
  --topic "贵州茅台财务表现与估值" \
  --sources ./materials/annual-report.pdf \
  --sources https://example.com/announcement \
  --stock-code 600519 \
  --data-cutoff 2026-06-30 \
  --source-type annual_report \
  --source-type announcement \
  --mode deep \
  --output ./reports
```

支持的常用参数：

| 参数 | 说明 |
| --- | --- |
| `--topic` | 研究问题 |
| `--sources` | 本地文件、文件夹或 URL，可重复使用 |
| `--output` | 研报输出目录 |
| `--web` / `--no-web` | 启用或关闭网络搜索 |
| `--max-results` | 网络搜索结果数量 |
| `--mode` | `quick`、`standard` 或 `deep` |
| `--stock-code` | 证券代码 |
| `--data-cutoff` | 数据截止日期，格式为 `YYYY-MM-DD` |
| `--source-type` | 资料类型，可重复使用 |

### 研报问答

通过研报 ID 提问：

```bash
uv run research-agent chat \
  --report-id report_xxxxxxxxxxxx \
  --question "最核心的投资逻辑是什么？"
```

也可以直接导入 Markdown 研报：

```bash
uv run research-agent chat \
  --report ./reports/company.md \
  --question "主要风险是什么？"
```

### 查看研报和任务

```bash
uv run research-agent list
uv run research-agent status task_xxxxxxxxxxxx
```

## 启动 API 服务

```bash
uv run research-agent serve --host 127.0.0.1 --port 8000
```

启动后访问：

```text
http://127.0.0.1:8000/docs
```

该页面提供完整的交互式 API 文档，可用于创建研报、查看任务、管理研报和发起问答。

## 配置

命令行和 API 默认读取项目根目录的 `.env`。macOS App 可以直接在设置页面中修改配置。

### 模型

```dotenv
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://your-api-endpoint/v1
OPENAI_MODEL=your_model
```

### 网络搜索

按需配置一个或多个搜索服务：

```dotenv
TAVILY_API_KEYS=your_tavily_key
BRAVE_API_KEYS=your_brave_key
SERPAPI_API_KEYS=your_serpapi_key
```

多个 Key 使用英文逗号分隔。

### 可选配置

```dotenv
EMBEDDING_API_KEY=your_embedding_key
EMBEDDING_BASE_URL=https://your-embedding-endpoint/v1
EMBEDDING_MODEL=your_embedding_model

RERANK_API_KEY=your_rerank_key
RERANK_BASE_URL=https://your-rerank-endpoint
RERANK_MODEL=your_rerank_model
```



## 运行测试

```bash
uv run pytest
```

## 更新日志

### 2026-07-01

- 修复重新打开研报后，对话历史没有自动加载的问题。
- 改善 SSL 和临时网络错误下的研报生成稳定性。
- 完成独立 macOS App 打包，最终用户不再需要安装 Python 或 `uv`。
- macOS App 默认使用 `~/.stock_researcher/` 保存配置和数据。
- 研报输出参数调整为目录地址，研报文件自动使用标题命名。

### 0.1.0 — 2026-06-30

- 发布首个可用原型。
- 提供 CLI、HTTP API 和原生 macOS App。
- 支持本地资料、网页链接和网络搜索。
- 支持三种研报深度、来源引用和风险分析。
- 支持后台任务、研报管理和多轮问答。
- 增加 `INFO=DEBUG` 详细日志开关。

## 注意事项

- 当前独立 macOS App 仅提供 Apple Silicon 版本。
- 部分网页可能因付费墙、登录要求或访问限制而无法读取完整内容。
- 重要结论应结合公司公告、财务报告和监管文件进行复核。
- 生成内容仅供研究参考，不构成投资建议。
