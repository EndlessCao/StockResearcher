# Stock Research Agent

基于 `FRAMEWORK.md` 的可运行原型：支持本地资料与网络检索、研究规划、Markdown 研报生成、引用追溯、SQLite 持久化，以及基于研报的多轮问答。当前提供 CLI、FastAPI 和原生 macOS 客户端。

## macOS 客户端

客户端支持服务与研报默认配置、研报生成、重命名/置顶/删除，以及基于研报的多轮 QA。首次运行会自动在当前项目目录通过 `uv` 启动 FastAPI；模型、搜索、向量、重排和行情配置可以在“设置 → 模型与数据”中修改，并写回项目根目录的 `.env`。
运行要求为 macOS 14+、匹配的 Xcode Command Line Tools 和已安装的 `uv`。

```bash
./script/build_and_run.sh
```

构建产物位于 `dist/StockResearcher.app`。也可以使用 Codex 的 `Run` 操作启动；进程验证使用：

```bash
./script/build_and_run.sh --verify
```

## 快速开始

```bash
uv sync
uv run research-agent report \
  --topic "分析英伟达未来三年的增长潜力" \
  --mode standard \
  --stock-code NVDA \
  --data-cutoff 2026-06-30 \
  --output ./reports
```

使用本地资料并关闭网络检索：

```bash
uv run research-agent report \
  --topic "分析某公司的竞争优势与主要风险" \
  --sources ./data/raw \
  --no-web \
  --output ./reports
```

`--output` 接收目录地址。研报文件名自动使用模型生成的研报标题，例如 `./reports/英伟达AI芯片业务深度研报.md`；标题中的文件系统非法字符会替换为下划线。

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

### 基于研报的多轮对话

对话按研报 ID 保存到 SQLite。每轮会自动注入研报正文和最近 10 条历史消息，模型可以自行决定是否调用：

- `rag_search`：查询该研报对应的 Chroma 原始资料，继续使用证券代码、数据截止日和资料类型过滤。
- `web_search`：通过现有 Tavily、Brave 或 SerpAPI Connector 查询研报之外的最新信息。

回答会区分研报观点、RAG 原始证据和网络新增信息，并分别使用 `[S1]`、`[W1]` 等编号。单轮最多执行 4 轮工具调用，避免无限循环。

```bash
uv run research-agent chat \
  --report-id report_xxxxxxxxxxxx \
  --question "这个风险对应的原始公告证据是什么？"

uv run research-agent chat \
  --report-id report_xxxxxxxxxxxx \
  --question "再搜索一下研报数据截止日之后的新变化"
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
- `PATCH /api/v1/reports/{report_id}`：重命名或设置置顶状态
- `DELETE /api/v1/reports/{report_id}`：删除研报及关联数据
- `GET/PUT /api/v1/config/environment`：读取或更新允许的 `.env` 配置（仅限本机访问）
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
模型写作阶段使用 `[S1]`，最终 Markdown 会转换为可点击的 `[[S1]](#ref-s1)`，并链接到“参考来源与证据”中的对应锚点。

默认 `standard` 模式。`quick` 适合快速验证，`deep` 会产生更多章节和模型调用。

## Chroma 混合检索

资料切分后持久化到 `data/chroma/`。大纲生成后，每章独立生成 4 个问题，覆盖核心事实、指标趋势、因果机制和风险/反方观点。每章的检索流程为：

1. 按 `stock_code`、`published_at <= data_cutoff` 和允许的 `source_type` 进行 Chroma metadata 过滤。
2. 合并向量召回和 BM25 关键词召回，证券代码、财务指标及年份可以通过精确词项进入候选集。
3. 对最多 30 个候选加入时间衰减和来源权威性评分。
4. 使用 rerank 模型重排，默认保留 10 个证据块。
5. 单一文档最多保留 3 个块，并优先选择风险/反方问题命中的候选。

```bash
uv run research-agent report \
  --topic "贵州茅台财务表现与估值" \
  --stock-code 600519 \
  --data-cutoff 2026-06-30 \
  --source-type annual_report \
  --source-type quarterly_report \
  --source-type announcement \
  --source-type research
```

## 配置

程序自动读取项目根目录 `.env`。已支持：

- 模型：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`LITELLM_MODEL`
- 搜索：`TAVILY_API_KEYS`、`BRAVE_API_KEYS`、`SERPAPI_API_KEYS`，按 Tavily → Brave → SerpAPI 自动选择
- 行情扩展：`ALPACA_API_KEY`、`ALPACA_SECRET_KEY`、`ALPACA_DATA_BASE_URL`、`ALPACA_DATA_FEED`
- 情绪扩展预留：`SOCIAL_SENTIMENT_API_KEY`、`SOCIAL_SENTIMENT_API_URL`
- 向量模型：`EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`
- 重排模型：`RERANK_API_KEY`、`RERANK_BASE_URL`、`RERANK_MODEL`
- 详细日志：只有设置 `INFO=DEBUG` 时才输出应用的 `INFO` 流程日志；未设置时只输出 `WARNING` 及以上

多个搜索 Key 可用英文逗号分隔，原型默认使用第一个。模型未配置时仍可运行，会输出证据摘要版研报与检索片段，不会伪造分析。
`LITELLM_MODEL` 若使用 `openai/model-name` 或 `deepseek/model-name` 形式，程序会在直连 OpenAI 兼容端点时自动移除提供商前缀。

设置 `INFO=DEBUG` 后，CLI 和 FastAPI 会输出任务规划、搜索 API、网页抓取、LLM 调用、章节并行写作、报告校验与文件入库日志。日志只记录模型名、耗时、字符数、Token 用量和 HTTP 状态等元信息，不输出 API Key 或完整提示词。

## 当前边界

- Chroma 保存原始资料向量；SQLite 保存任务、来源、研报、引用和对话元数据。
- Redis、异步任务队列、金融/情绪综合分析、PDF/DOCX 导出和 macOS 应用留到下一阶段。
- 网络来源会尽量抓取正文；抓取失败时保留搜索摘要，并标记为未验证来源。

## 开发验证

```bash
uv run pytest
```
