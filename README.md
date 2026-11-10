# CodeEval · 工程代码质量评审平台

基于 LLM（DeepSeek）+ LangGraph 多智能体的工程代码质量评审系统。上传 zip 包或提供 Git 仓库地址，平台自动进行六维代码质量评审并授予「程序员圈内梗」称号。

## 1. 项目概览

| 项 | 说明 |
|---|---|
| 定位 | 工程代码质量评审（输入：Git 仓库 / zip 多文件工程） |
| 评审方式 | 静态分析（radon/bandit）+ LLM 六维深度评审 + RAG 规范判据 |
| 差异化 | 抽象称号系统（10 级段位 + 彩蛋称号 + AI 颁奖词） |
| 输出 | 六维评分、可定位到文件/行的问题清单、能力画像 |

## 2. 技术栈

**后端**：Python 3.12 · FastAPI · LangChain / LangGraph 1.0 · DeepSeek（OpenAI 兼容）· SQLAlchemy 2.0(asyncio) · asyncpg · PostgreSQL · Milvus · sentence-transformers · radon + bandit

**前端**：Vue 3 · Vite 6 · Element Plus · Vue Router 4 · Axios

**基础设施**：Docker Compose（PostgreSQL / etcd / MinIO / Milvus / backend）

## 3. 系统架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                           前端（Vue 3 + Vite）                        │
│   UploadView(提交) · ReportView(报告) · HistoryView(历史) ·           │
│   ProfileView(能力画像)                                               │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTP /api/v1（Vite 代理 → 8001）
┌───────────────────────────────▼──────────────────────────────────────┐
│                      后端（FastAPI + uvicorn）                        │
│                                                                      │
│  api/                接口层                                           │
│    ├─ review.py      提交/查询评审（异步后台任务）                      │
│    └─ profile.py     能力画像聚合                                      │
│                                                                      │
│  clerk/              评审引擎（LangGraph 状态机）                      │
│    graph.py   parse → lint → review → award                          │
│    parser.py  安全解压 · 语言识别 · 三层分区 · 重复块检测              │
│    linters.py radon(复杂度/维护指数) + bandit(安全)                    │
│    nodes.py   图节点：解析/静态分析/LLM评审/称号                       │
│    profiler.py 六维能力画像（规则计算，不依赖 LLM）                    │
│    prompts.py 评分维度定义 + Prompt                                   │
│                                                                      │
│  rag/                RAG 规范知识库                                   │
│    embedder.py  all-MiniLM-L6-v2 文本向量化                           │
│    milvus_client.py  Milvus collection/upsert/检索                    │
│    retriever.py  高层检索接口                                         │
│                                                                      │
│  core/               基础设施                                         │
│    llm_factory.py   DeepSeek 模型工厂（按业务类型路由/缓存）           │
│    retry.py         三层兜底：重试 → 降级 → 系统兜底                   │
│    memory.py        MemorySaver 检查点 + thread_id                    │
│    logger.py        结构化日志 · exceptions.py 异常体系                 │
│                                                                      │
│  db/                 数据持久化                                       │
│    models.py        submissions + reviews（JSONB）                    │
│    session.py       异步引擎/Session 工厂 · migrations.py 幂等迁移    │
└───────┬──────────────────┬──────────────────────┬────────────────────┘
        │ SQLAlchemy/asyncpg│                       │ HTTP
┌───────▼──────┐  ┌────────▼──────┐  ┌─────────────▼─────────────────┐
│ PostgreSQL   │  │ Milvus(向量库) │  │ DeepSeek API（OpenAI 兼容）    │
│ submissions  │  │ + etcd + MinIO │  │ 六维评审 / 颁奖词生成          │
│ reviews      │  │ 规范文档切片   │  │                               │
└──────────────┘  └───────────────┘  └───────────────────────────────┘
```

## 4. 评审流程

输入 zip/Git 仓库后，后端以异步后台任务驱动一条 LangGraph 状态机流水线：

```
提交评审 POST /api/v1/review/
   │  (1) 创建 submission(pending) + 启动后台任务
   ▼
git clone（如需，depth=1）
   │
   ▼
┌─ parse ────────────────────────────────────────────────┐
│ 安全解压(zip炸弹/路径穿越防护) → 语言识别 → 三层分区       │
│  · focus_layer     焦点层（入口+体量优先，受 token 预算约束）│
│  · structure_layer 结构层（轻量静态分析概览）             │
│  · 忽略层（node_modules/dist/二进制等，仅统计）          │
│  + 跨文件重复块检测                                      │
└──────────────┬─────────────────────────────────────────┘
               ▼
┌─ lint ─────────────────────────────────────────────────┐
│ radon：圈复杂度 / 维护指数 / 函数级指标                    │
│ bandit：安全漏洞扫描                                     │
│ 巨文件（>2000 行）→ 函数级摘要，不硬塞全文                │
└──────────────┬─────────────────────────────────────────┘
               ▼
┌─ review ────────────────────────────────────────────────┐
│ 组装 Prompt（代码 + 结构概览 + 静态指标 + RAG 规范判据）   │
│ RAG：查询文本 → embedding → Milvus dense 检索 → 官方规范   │
│ LLM 结构化输出六维评分（function_calling，Pydantic 约束）  │
└──────────────┬─────────────────────────────────────────┘
               ▼
┌─ award ────────────────────────────────────────────────┐
│ 总分映射 10 级段位称号 + 规则触发彩蛋 + LLM 生成颁奖词     │
└──────────────┬─────────────────────────────────────────┘
               ▼
落库（submissions 统计 + reviews 结果）→ 状态 completed
               ▼
前端轮询 GET /api/v1/review/{id} 展示报告
```

## 5. 评分维度（满分 100）

| 维度 Key | 名称 | 权重 | 数据来源 |
|---|---|---|---|
| structure | 结构·模块化 | 20 | 目录树 + 焦点层 + 静态 |
| robustness | 健壮性·安全 | 20 | 焦点层 LLM + 静态 |
| maintainability | 可维护·设计 | 20 | 焦点层 LLM（SOLID/DRY/设计模式） |
| complexity | 复杂度·重复 | 15 | 静态规则（圈复杂度/重复块/函数行数） |
| style | 规范·风格 | 15 | 焦点层 + RAG 官方规范判据 |
| readability | 可读·注释 | 10 | 焦点层 LLM |

每维度统一产出 `DimensionScore`：`{dimension, score, weight, issues: [{file, line, severity, evidence, suggestion}]}`。

## 6. 称号系统

总分→10 级段位（`clerk/nodes.py` 的 `TITLE_LEVELS`），另凭静态特征触发彩蛋称号（如「巨石镇守者」），最后由 LLM 生成一句「程序员圈内梗」风格颁奖词。

## 7. 数据模型

- **submissions**：提交记录（id / user_id / language / 分区统计 / status / error / created_at）
- **reviews**：评审结果（total_score / summary / title / level / easter_egg / reason / dimension_scores(JSONB) / static_metrics(JSONB)）

## 8. 目录结构

```
code-eval-platform/
├── backend/            # FastAPI 后端
│   ├── main.py         # 应用入口（lifespan 迁移 + CORS + 路由）
│   ├── config.py       # 配置中心（pydantic-settings，读 .env.local）
│   ├── api/            # 接口层（v1/review、v1/profile）
│   ├── clerk/          # 评审引擎（LangGraph 图 + 节点 + 解析 + 静态分析）
│   ├── rag/            # RAG 规范知识库
│   ├── core/           # LLM 工厂 / 重试兜底 / 日志 / 异常 / MemorySaver
│   └── db/             # 数据模型 / Session / 迁移
├── frontend/           # Vue 3 前端
│   └── src/{views,api,router}
├── scripts/build_kb.py # 构建规范知识库脚本
├── docs/               # 设计文档
├── docker-compose.yml  # PG / etcd / MinIO / Milvus / backend
└── Dockerfile          # 后端镜像（CPU 版 torch + 依赖分层缓存）
```

## 9. 快速开始

### 9.1 启动基础设施 + 后端（Docker）

```bash
# 1. 准备外部数据卷（compose 中 pgdata 声明为 external）
docker volume create code_eval_pgdata

# 2. 配置环境变量：复制 .env.example 为 .env.local 并填入 DeepSeek Key
cp .env.example .env.local

# 3. 启动全部服务
docker-compose up -d
```

### 9.2 构建规范知识库（评审「规范·风格」维度的评审判据）

```bash
docker exec code_eval_backend python scripts/build_kb.py
```

### 9.3 启动前端

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173，/api 代理至 8001
```

### 9.4 本机直跑后端（可选）

```bash
pip install -r requirements.txt
pip install torch==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu
uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

## 10. 配置项（`.env.local`）

| 变量 | 说明 | 默认 |
|---|---|---|
| DEEPSEEK_API_KEY / BASE_URL / MODEL | LLM 接入 | — / api.deepseek.com / deepseek-chat |
| REVIEW_TOKEN_BUDGET | 单次评审 LLM token 预算 | 60000 |
| REVIEW_FOCUS_FILE_LIMIT | 焦点层文件数上限 | 15 |
| REVIEW_GIANT_FILE_LINES | 巨石文件阈值（行） | 2000 |
| REVIEW_UPLOAD_MAX_BYTES | 上传大小上限 | 200MB |
| DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD | PostgreSQL 连接 | localhost · 5433 · code_eval |
| MILVUS_HOST / MILVUS_PORT | 向量库连接 | localhost · 19530 |
| EMBEDDING_MODEL | 向量化模型 | all-MiniLM-L6-v2 |

## 11. 关键 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/v1/review/ | 提交评审（zip 文件或 git_url），返回 submission_id |
| GET | /api/v1/review/ | 某用户历史提交列表 |
| GET | /api/v1/review/{id} | 查询评审状态与结果 |
| GET | /api/v1/profile/{user_id} | 用户六维能力画像 |
| GET | /health | 健康检查 |

## 12. 弹性设计

- **异步评审**：提交即返回，后台任务执行，前端按 submission_id 轮询结果。
- **三层兜底**（`core/retry.py`）：自动重试（最多 2 次）→ 业务降级 → 系统兜底，保证 LLM 抖动不阻断服务。
- **非关键组件降级**：Milvus / 静态分析工具 / DB 不可用时仅记日志，不阻断主评审流程。
- **安全解压**：防 zip 炸弹（500MB 总量/50MB 单文件上限）+ 路径穿越校验。
- **Token 预算动态裁量**：焦点层按「入口 + 体量」排序，超预算自动滑入结构层，避免超上下文。
