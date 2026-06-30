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

1. 按 `quick / standard / deep` 生成 6 / 8 / 10 章判断式大纲，并锚定目标年份。
2. 按章节从现有资料中检索相关片段，建立带固定 `[S1]` 引用编号的证据包。
3. 并行撰写章节；每章执行“结论 → 证据 → 因果 → 判断边界”，并要求反方观点和预测措辞。
4. 单章超时只降级该章为证据摘要，不影响其他章节和最终报告交付。
5. 统一装配标题、元数据、目录、可信评估、参考来源和免责声明，并校验章节及引用完整性。

默认 `standard` 模式。`quick` 适合快速验证，`deep` 会产生更多章节和模型调用。

## 配置

程序自动读取项目根目录 `.env`。已支持：

- 模型：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`LITELLM_MODEL`
- 搜索：`TAVILY_API_KEYS`、`BRAVE_API_KEYS`、`SERPAPI_API_KEYS`，按 Tavily → Brave → SerpAPI 自动选择
- 行情扩展：`ALPACA_API_KEY`、`ALPACA_SECRET_KEY`、`ALPACA_DATA_BASE_URL`、`ALPACA_DATA_FEED`
- 情绪扩展预留：`SOCIAL_SENTIMENT_API_KEY`、`SOCIAL_SENTIMENT_API_URL`

多个搜索 Key 可用英文逗号分隔，原型默认使用第一个。模型未配置时仍可运行，会输出证据摘要版研报与检索片段，不会伪造分析。
`LITELLM_MODEL` 若使用 `openai/model-name` 或 `deepseek/model-name` 形式，程序会在直连 OpenAI 兼容端点时自动移除提供商前缀。

## 当前边界

- SQLite 已保存任务、来源、切片、研报、引用和对话；首版用轻量关键词检索替代 Chroma，避免额外服务依赖。
- Redis、异步任务队列、金融/情绪综合分析、PDF/DOCX 导出和 macOS 应用留到下一阶段。
- 网络来源会尽量抓取正文；抓取失败时保留搜索摘要，并标记为未验证来源。

## 开发验证

```bash
uv run pytest
```
