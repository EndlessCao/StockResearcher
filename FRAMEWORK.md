研报分析 Agent 应用架构描述

1. 项目目标

本项目旨在构建一个面向研报分析与深度研究的 Agent 应用。系统能够接入多类信息源，自动完成信息检索、资料整理、交叉验证、深度分析与研报生成，并支持用户基于已生成研报继续进行问答、追问和多轮分析。

应用需要同时支持两种使用方式：

1. CLI 命令行调用，便于开发者、研究员或自动化脚本集成。
2. macOS 桌面应用，便于普通用户进行可视化操作、研报管理和交互式问答。

2. 总体架构

系统采用分层架构设计，核心由信息源接入层、数据处理层、Agent 编排层、研报生成层、上下文问答层、应用接口层和存储层组成。

整体架构如下：

┌──────────────────────────────┐
│        CLI / macOS App        │
└───────────────┬──────────────┘
                │
┌───────────────▼──────────────┐
│        API / Command Layer     │
└───────────────┬──────────────┘
                │
┌───────────────▼──────────────┐
│        Agent Orchestrator      │
└───────┬────────┬────────┬─────┘
        │        │        │
        ▼        ▼        ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Research │ │ Analysis │ │ Report   │
│ Planner  │ │ Engine   │ │ Writer   │
└────┬─────┘ └────┬─────┘ └────┬─────┘
     │            │            │
┌────▼────────────▼────────────▼────┐
│        Knowledge / Context Layer   │
└────┬────────────┬────────────┬────┘
     │            │            │
     ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Sources  │ │ Vector DB│ │ Metadata │
│ Connectors│ │ / Index │ │ Store    │
└──────────┘ └──────────┘ └──────────┘

3. 核心模块

3.1 信息源接入层

信息源接入层负责连接外部数据源，并将原始资料标准化为系统内部可处理的文档格式。

支持的信息源包括：

* 本地文件：PDF、Word、Markdown、CSV、Excel、TXT。
* 网络信息源：网页、新闻、公告、研究报告、公司官网。
* 金融数据源：行情数据、财务报表、宏观经济数据。
* 数据库或内部知识库：企业私有文档、历史研报、投研笔记。
* API 数据源：第三方金融 API、搜索 API、新闻 API、公司数据库 API。

每一种信息源通过 Connector 方式接入，统一输出标准结构：

{
  "source_id": "unique_source_id",
  "source_type": "pdf/web/api/database",
  "title": "资料标题",
  "url": "来源地址",
  "content": "正文内容",
  "metadata": {
    "author": "作者",
    "published_at": "发布日期",
    "retrieved_at": "抓取时间",
    "source_reliability": "可信度评级"
  }
}

3.2 数据处理层

数据处理层负责对原始资料进行清洗、切分、结构化和索引。

主要能力包括：

* 文档解析：提取 PDF、网页、表格和报告正文。
* 文本清洗：去除噪声、页眉页脚、广告、重复内容。
* Chunk 切分：将长文档切分为适合检索和上下文注入的片段。
* 元数据抽取：识别公司、行业、时间、指标、数据来源等信息。
* 向量化索引：将文档片段写入向量数据库，支持语义检索。
* 关键词索引：支持精确搜索、代码搜索、公司名搜索和时间过滤。

3.3 Agent 编排层

Agent 编排层是系统核心，负责根据用户任务自动拆解研究路径，并调用不同工具完成研究。

核心 Agent 包括：

Research Planner

负责理解用户研究目标，并拆解研究任务。

例如：

用户输入：分析英伟达未来三年的增长潜力
Research Planner 拆解为：
1. 公司基本面分析
2. 财务表现分析
3. GPU / AI 芯片市场分析
4. 竞争格局分析
5. 风险因素分析
6. 估值与投资结论

Source Retriever

负责根据研究计划检索相关信息源，包括内部知识库、网络搜索、API 数据和本地文件。

Evidence Verifier

负责对关键事实进行交叉验证，避免研报中出现单一来源、过期信息或不可靠结论。

Analysis Engine

负责完成分析推理，包括：

* 行业趋势分析
* 公司基本面分析
* 财务指标分析
* 竞争对手对比
* 风险因素归纳
* 投资逻辑总结
* 观点生成与反驳检查

Report Writer

负责将分析结果组织成正式研报，支持不同模板和输出格式。

3.4 研报生成层

研报生成层负责把研究过程中的证据、分析和结论整理成结构化研报。

默认研报结构如下：

1. 摘要
2. 核心结论
3. 研究对象概览
4. 行业背景
5. 市场空间分析
6. 公司基本面分析
7. 财务表现分析
8. 竞争格局分析
9. 风险因素
10. 投资观点 / 战略建议
11. 引用来源
12. 附录

输出格式支持：

* Markdown
* PDF
* DOCX
* HTML
* JSON 结构化报告

每篇研报都需要保留引用来源，方便用户追溯事实依据。

3.5 上下文问答层

系统生成研报后，会将研报本身、引用资料、分析过程和关键结论写入上下文知识库。

用户可以继续进行多轮对话，例如：

用户：这篇研报中最大的风险是什么？
用户：请展开讲一下竞争格局。
用户：把估值部分改成更保守的假设。
用户：基于这篇研报生成一页投资摘要。

问答层采用 RAG 架构：

1. 用户提出问题。
2. 系统从研报、引用资料和原始文档中检索相关片段。
3. Agent 结合上下文生成回答。
4. 回答中保留引用和依据。
5. 必要时重新触发补充研究。

3.6 存储层

系统需要维护以下数据：

* 原始文档存储：保存用户上传或抓取的资料。
* 向量数据库：存储文档 chunk embedding。
* 元数据库：保存文档来源、任务状态、研报记录、引用关系。
* 报告存储：保存生成的 Markdown、PDF、DOCX 等文件。
* 会话存储：保存用户与 Agent 的多轮对话上下文。
* 任务日志：记录 Agent 的研究路径、工具调用和错误信息。

推荐技术选型：

对象存储：Local FS / S3 / MinIO
元数据库：PostgreSQL / SQLite
向量数据库：Qdrant / LanceDB / Chroma
任务队列：Celery / Redis Queue / Temporal
日志系统：OpenTelemetry / Logfire / LangSmith

4. 应用接口层

4.1 CLI 调用

CLI 主要用于命令行研究任务、自动化脚本和开发调试。

示例命令：

research-agent report \
  --topic "分析苹果公司未来三年的增长潜力" \
  --sources ./data/apple_reports \
  --output ./reports/apple_research.md

支持能力：

* 创建研究任务
* 指定信息源
* 指定报告模板
* 导出研报
* 基于已有研报问答
* 查看任务状态
* 批量生成报告

示例：

research-agent chat \
  --report ./reports/apple_research.md \
  --question "这篇研报中最核心的投资逻辑是什么？"

4.2 macOS 桌面应用

macOS 应用面向普通用户，提供可视化交互能力。

核心功能包括：

* 信息源管理
* 文件拖拽上传
* 研究任务创建
* 研报生成进度查看
* 研报阅读与编辑
* 基于研报的聊天问答
* 引用来源查看
* 报告导出
* 本地知识库管理

推荐技术方案：

前端：SwiftUI / Tauri / Electron
本地服务：Python FastAPI / Node.js
本地数据库：SQLite + LanceDB
模型调用：OpenAI API / 本地模型 / 企业模型网关

如果优先考虑原生体验，可以选择 SwiftUI。

如果希望复用 Web 前端和 CLI 后端，可以选择 Tauri 或 Electron。

5. 推荐技术架构

后端

语言：Python
API 框架：FastAPI
Agent 框架：LangGraph / LlamaIndex / 自研 Orchestrator
文档解析：PyMuPDF / Unstructured / MarkItDown
向量数据库：Qdrant / LanceDB
数据库：PostgreSQL / SQLite
任务队列：Celery / Redis Queue
模型接口：OpenAI API / Anthropic / 本地 LLM

CLI

CLI 框架：Typer / Click
配置管理：Pydantic Settings
输出格式：Markdown / JSON / Rich Console

macOS

方案一：SwiftUI + 本地 FastAPI 服务
方案二：Tauri + React + Python 后端
方案三：Electron + React + Node/Python 后端

推荐优先方案：

CLI + FastAPI + LangGraph + LanceDB + SQLite + Tauri

该方案兼顾开发效率、跨端复用、本地化部署和桌面应用体验。

6. 典型工作流

6.1 生成研报流程

1. 用户输入研究主题
2. 用户选择或上传信息源
3. Research Planner 拆解研究任务
4. Source Retriever 检索相关资料
5. Data Processor 清洗和索引文档
6. Analysis Engine 进行分析
7. Evidence Verifier 校验关键事实
8. Report Writer 生成研报
9. 系统保存研报、引用和上下文
10. 用户导出或继续对话

6.2 基于研报问答流程

1. 用户选择一篇已有研报
2. 用户提出问题
3. 系统检索研报正文和引用资料
4. Agent 结合上下文生成回答
5. 回答附带引用依据
6. 用户继续追问或要求修改研报

7. 核心数据模型

ResearchTask

{
  "id": "task_id",
  "topic": "研究主题",
  "status": "pending/running/completed/failed",
  "sources": ["source_id"],
  "created_at": "创建时间",
  "completed_at": "完成时间"
}

SourceDocument

{
  "id": "source_id",
  "title": "资料标题",
  "type": "pdf/web/api",
  "content_path": "原始内容地址",
  "metadata": {},
  "created_at": "创建时间"
}

Report

{
  "id": "report_id",
  "task_id": "task_id",
  "title": "研报标题",
  "content": "研报正文",
  "format": "markdown/pdf/docx",
  "citations": [],
  "created_at": "创建时间"
}

Conversation

{
  "id": "conversation_id",
  "report_id": "report_id",
  "messages": [],
  "created_at": "创建时间"
}

8. 关键设计原则

1. 信息源与 Agent 解耦
    每个信息源通过 Connector 接入，Agent 不直接依赖具体数据源。
2. 研报生成过程可追溯
    每个结论都应能够追溯到原始资料、引用片段和分析过程。
3. 支持本地优先
    CLI 与 macOS 应用均应支持本地文件、本地数据库和本地索引。
4. 支持扩展
    后续可以新增行业模板、财务模型、数据源 Connector 和模型供应商。
5. 支持人机协作
    用户可以调整研究方向、补充资料、修改假设、重写结论。

9. MVP 建议

第一阶段可以优先实现以下能力：

1. CLI 创建研究任务
2. 支持本地 PDF / Markdown / 网页 URL 作为信息源
3. 文档解析、切分、向量索引
4. 基于 RAG 的资料检索
5. 自动生成 Markdown 研报
6. 基于研报进行问答
7. SQLite + LanceDB 本地存储
8. macOS 桌面端完成上传、生成、阅读、问答

第二阶段再扩展：

1. 金融数据 API 接入
2. 自动网络搜索
3. 多 Agent 协作
4. 引用可信度评分
5. PDF / DOCX 导出
6. 研报模板系统
7. 团队协作和云端同步

10. 总结

该项目的核心不是简单的文档问答，而是一个完整的研究型 Agent 系统。它需要同时具备信息源接入、资料理解、任务规划、深度分析、研报生成、引用追溯和上下文对话能力。

推荐采用“本地优先 + 可扩展 Connector + Agent Orchestrator + RAG 上下文问答”的架构。这样既可以满足 CLI 自动化调用，也可以支持 macOS 桌面应用中的交互式研究体验。

数据源与存储架构补充说明

1. 网络信息源接入

系统网络信息源通过统一的 Search Connector 层接入，支持多搜索服务适配：

Search Connector
├── Tavily Connector
├── Brave Search Connector
├── SerpAPI Connector
└── SearXNG Connector

各 Connector 统一输出标准搜索结果结构：

{
  "provider": "tavily/brave/serpapi/searxng",
  "query": "搜索关键词",
  "title": "结果标题",
  "url": "来源链接",
  "snippet": "摘要",
  "published_at": "发布时间",
  "retrieved_at": "抓取时间"
}

网络检索模块负责根据研究任务自动选择或组合多个搜索源，并对搜索结果进行去重、排序、可信度评估和正文抓取。

2. 金融数据源接入

金融数据源通过 Financial Data Connector 层统一接入，支持：

Financial Data Connector
├── Efinance Connector
├── YFinance Connector
├── Alpaca Market Data Connector
└── AkShare Connector

主要支持的数据类型包括：

* 股票行情数据
* 历史 K 线数据
* 财务报表数据
* 指数与行业数据
* 宏观经济数据
* 公司基本面数据
* 市场交易数据

统一输出结构：

{
  "provider": "yfinance/akshare/efinance/alpaca",
  "symbol": "AAPL",
  "market": "US/CN/HK",
  "data_type": "price/financials/macro/index",
  "data": {},
  "retrieved_at": "抓取时间"
}

3. 情绪面信息源接入

情绪面信息通过 Sentiment Connector 层接入，优先支持 Adanos API。

Sentiment Connector
└── Adanos API Connector

该模块主要用于获取：

* 公司舆情
* 新闻情绪
* 社交媒体情绪
* 市场情绪指标
* 行业关注度变化
* 风险事件信号

统一输出结构：

{
  "provider": "adanos",
  "target": "研究对象",
  "sentiment_score": 0.72,
  "sentiment_label": "positive/neutral/negative",
  "summary": "情绪面摘要",
  "signals": [],
  "retrieved_at": "抓取时间"
}

4. 存储架构

本项目采用本地优先的轻量级存储架构：

┌─────────────────────────────┐
│          Storage Layer       │
├─────────────────────────────┤
│ SQLite     普通关系型数据     │
│ Chroma     向量检索数据库     │
│ Redis      缓存与任务状态     │
│ Local FS   原始文件与报告文件 │
└─────────────────────────────┘

4.1 SQLite

SQLite 负责保存结构化业务数据：

* 用户配置
* 数据源配置
* 研究任务
* 报告元信息
* 文档元信息
* 引用关系
* 会话记录
* Agent 工具调用日志

4.2 Chroma

Chroma 负责保存向量化后的文档片段，用于 RAG 检索。

主要集合包括：

chroma_collections
├── source_documents
├── report_chunks
├── conversation_memory
└── research_notes

其中：

* source_documents：原始资料切片。
* report_chunks：生成后的研报切片。
* conversation_memory：用户与 Agent 的问答上下文。
* research_notes：Agent 中间分析笔记和阶段性结论。

4.3 Redis

Redis 用于缓存和运行时状态管理：

* 搜索结果缓存
* 金融数据缓存
* 情绪数据缓存
* Agent 任务状态
* 临时上下文
* 队列任务状态
* 限流计数
* API 调用结果缓存

4.4 Local File System

本地文件系统保存较大的非结构化文件：

data/
├── raw/          原始上传文件
├── parsed/       解析后的文本
├── reports/      生成的研报
├── exports/      PDF / DOCX / HTML 导出文件
└── cache/        临时文件缓存

5. 更新后的整体架构

┌────────────────────────────────────────┐
│          CLI / macOS Desktop App        │
└───────────────────┬────────────────────┘
                    │
┌───────────────────▼────────────────────┐
│          API / Command Interface         │
└───────────────────┬────────────────────┘
                    │
┌───────────────────▼────────────────────┐
│             Agent Orchestrator           │
├────────────────────────────────────────┤
│ Research Planner                         │
│ Source Retriever                         │
│ Financial Analyzer                       │
│ Sentiment Analyzer                       │
│ Evidence Verifier                        │
│ Report Writer                            │
│ Report QA Agent                          │
└───────────┬──────────────┬─────────────┘
            │              │
            ▼              ▼
┌───────────────────┐  ┌───────────────────┐
│   Connector Layer │  │   Knowledge Layer  │
├───────────────────┤  ├───────────────────┤
│ Tavily            │  │ Chroma Vector DB   │
│ Brave             │  │ SQLite Metadata DB │
│ SerpAPI           │  │ Redis Cache        │
│ SearXNG           │  │ Local FS           │
│ Efinance          │  └───────────────────┘
│ YFinance          │
│ Alpaca Market Data│
│ AkShare           │
│ Adanos API        │
└───────────────────┘

6. 配置设计

系统通过统一配置文件管理各类数据源。

示例：

search:
  enabled_providers:
    - tavily
    - brave
    - serpapi
    - searxng
  tavily:
    api_key: ${TAVILY_API_KEY}
  brave:
    api_key: ${BRAVE_API_KEY}
  serpapi:
    api_key: ${SERPAPI_API_KEY}
  searxng:
    base_url: http://localhost:8080
financial:
  enabled_providers:
    - efinance
    - yfinance
    - alpaca
    - akshare
  alpaca:
    api_key: ${ALPACA_API_KEY}
    api_secret: ${ALPACA_API_SECRET}
sentiment:
  enabled_providers:
    - adanos
  adanos:
    api_key: ${ADANOS_API_KEY}
storage:
  sqlite:
    path: ./data/app.db
  chroma:
    persist_directory: ./data/chroma
  redis:
    url: redis://localhost:6379/0

7. 数据流说明

1. 用户输入研究主题
2. Agent Planner 拆解研究任务
3. Source Retriever 调用 Tavily / Brave / SerpAPI / SearXNG 检索网络资料
4. Financial Analyzer 调用 Efinance / YFinance / Alpaca / AkShare 获取金融数据
5. Sentiment Analyzer 调用 Adanos API 获取情绪面信息
6. Data Processor 清洗、解析、去重、切片
7. 文档片段写入 Chroma
8. 任务、文档、引用、报告元信息写入 SQLite
9. 高频查询和外部 API 结果写入 Redis 缓存
10. Report Writer 生成研报
11. 用户基于研报继续问答

8. 架构定位

更新后的系统定位为：

一个面向金融与产业研究场景的 Deep Research Agent，
通过多搜索引擎、多金融数据源、情绪数据源和本地知识库，
完成自动研究、分析推理、研报生成和基于研报的持续问答。