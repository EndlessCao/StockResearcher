# Stock Research Agent

基于 `FRAMEWORK.md` 的可运行原型：支持本地资料与网络检索、研究规划、Markdown 研报生成、引用追溯、SQLite 持久化，以及基于研报的多轮问答。当前提供 CLI 和 FastAPI，不包含 macOS 客户端。

## 快速开始

```bash
uv sync
uv run research-agent report \
  --topic "分析英伟达未来三年的增长潜力" \
  --mode standard \
  --output ./reports/nvidia.md
```

使用本地资料并关闭网络检索：

```bash
uv run research-agent report \
  --topic "分析某公司的竞争优势与主要风险" \
  --sources ./data/raw \
  --no-web \
  --output ./reports/company.md
```

针对研报问答：

```bash
uv run research-agent chat \
  --report-id report_xxxxxxxxxxxx \
  --question "最核心的投资逻辑是什么？"
```

也可以直接导入已有 Markdown：

```bash
uv run research-agent chat --report ./reports/company.md --question "主要风险是什么？"
```

## API

```bash
uv run research-agent serve --port 8000
```

启动后访问 `http://127.0.0.1:8000/docs`。主要接口：

- `POST /api/v1/reports`：同步创建研报
- `GET /api/v1/reports`：研报列表
- `GET /api/v1/reports/{report_id}`：研报详情
- `POST /api/v1/reports/{report_id}/chat`：研报问答
- `GET /api/v1/tasks/{task_id}`：任务状态

创建研报示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/reports \
  -H 'Content-Type: application/json' \
  -d '{"topic":"分析苹果公司未来三年的增长潜力","mode":"standard","web_search":true,"max_search_results":6}'
```

## 专业研报写作流程

写作部分参考 `tmp/deep-research` 的质量规范，但继续使用本项目既有的本地文件、URL、Tavily、Brave 和 SerpAPI 信息源：

1. 大纲模型只返回 `title` 和 `chapters[].title/focus`。程序去除 JSON 围栏后使用 `json.loads()` 校验，再按 `quick / standard / deep` 补齐或裁剪为 6 / 8 / 10 章；无效 JSON 完全回退到固定大纲。
2. 按章节从现有资料中检索相关片段，建立带固定 `[S1]` 引用编号的证据包。
3. 并行撰写章节；每章执行“核心判断 → 事实 → 因果 → 判断”，要求区分实际数据、机构预期和情景假设，并包含反方观点。
4. 某章完全没有 `[Sx]` 时追加严格约束并重写一次；第二次仍无引用只记录 QA 告警，不继续重写。
5. 标题、元数据、研究问题、目录、编号章节、参考来源与证据、免责声明全部由代码装配。非法 `[S99]` 只记录 QA 告警并保留原文。

QA 告警保存在研报记录的 `qa_warnings` 字段中。QA 不通过不会阻止报告保存，任务仍返回成功。

默认 `standard` 模式。`quick` 适合快速验证，`deep` 会产生更多章节和模型调用。

## 配置

程序自动读取项目根目录 `.env`。已支持：

- 模型：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`LITELLM_MODEL`
- 搜索：`TAVILY_API_KEYS`、`BRAVE_API_KEYS`、`SERPAPI_API_KEYS`，按 Tavily → Brave → SerpAPI 自动选择
- 行情扩展：`ALPACA_API_KEY`、`ALPACA_SECRET_KEY`、`ALPACA_DATA_BASE_URL`、`ALPACA_DATA_FEED`
- 情绪扩展预留：`SOCIAL_SENTIMENT_API_KEY`、`SOCIAL_SENTIMENT_API_URL`
- 日志级别：`LOG_LEVEL`，默认 `INFO`

多个搜索 Key 可用英文逗号分隔，原型默认使用第一个。模型未配置时仍可运行，会输出证据摘要版研报与检索片段，不会伪造分析。
`LITELLM_MODEL` 若使用 `openai/model-name` 或 `deepseek/model-name` 形式，程序会在直连 OpenAI 兼容端点时自动移除提供商前缀。

CLI 和 FastAPI 默认输出研报生成流程日志，包括任务规划、搜索 API、网页抓取、LLM 调用、章节并行写作、报告校验与文件入库。日志只记录模型名、耗时、字符数、Token 用量和 HTTP 状态等元信息，不输出 API Key 或完整提示词。

## 当前边界

- SQLite 已保存任务、来源、切片、研报、引用和对话；首版用轻量关键词检索替代 Chroma，避免额外服务依赖。
- Redis、异步任务队列、金融/情绪综合分析、PDF/DOCX 导出和 macOS 应用留到下一阶段。
- 网络来源会尽量抓取正文；抓取失败时保留搜索摘要，并标记为未验证来源。

## 开发验证

```bash
uv run pytest
```
