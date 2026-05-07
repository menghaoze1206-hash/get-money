# AGENTS.md

本文件为 OpenCode 在本仓库中工作时提供指导。

## 项目概览

股息率择时系统，包含 FastAPI 后端 + React 前端 Web 面板。工作日检测 ETF/基金股息率，通过微信（企业微信或 PushPlus）推送买入信号。**不使用定投 DCA，只在股息率够便宜时提示一次性加仓。** 同时记录历史信号，根据用户配置的月预算自动计算建议日投金额。

完整策略公式、API 依赖和演进历史见 `ARCHITECTURE.md`。

## 命令

```bash
# ── 通知引擎 ──
# 本地运行一次（使用环境变量中的 WeCom Key）
python3 notify.py

# 通过 shell 封装运行（设置 WECOM_KEY，日志写入 data/notify.log）
./scripts/run.sh

# 快速测试（检查当前 NOTIFY_TYPE 的环境变量）
./scripts/test.sh

# 安装本地 cron（Mac，北京时间工作日 9:30）
./scripts/install_cron.sh

# ── Web 面板 ──
# 完整启动：构建前端，在 http://localhost:8000 启动 FastAPI
./scripts/start_web.sh

# 开发模式（仅前端，代理到 localhost:8000 后端）
cd frontend && npm run dev

# 前端 lint 和构建
cd frontend && npm run lint
cd frontend && npm run build
```

**Python 依赖**: `pip install akshare fastapi uvicorn`（akshare 非必须但建议安装，见下方懒加载说明）。

**Python 导入路径**: 运行 `backend/` 模块时，`PYTHONPATH` 必须包含项目根目录（例如 `scripts/start_web.sh` 设置了 `export PYTHONPATH="$PROJECT_DIR"`）。否则 `from backend.database import ...` 会失败。

**前端开发流程**: Vite 开发服务器运行在 5173 端口，配置代理 `/api` → `localhost:8000`。先在 8000 端口启动 `uvicorn backend.main:app`，再在 `frontend/` 中执行 `npm run dev`。

**环境变量**:
- `WECOM_KEY`（企业微信通知必需）
- `NOTIFY_TYPE`（默认 `wecom`，也支持 `pushplus`）
- `PUSHPLUS_TOKEN`（使用 PushPlus 时设置）
- `MONTHLY_INVEST_BUDGET`（可选；优先级高于 SQLite 中的设置）

## 架构

三层结构：

```
notify.py (822 行)           backend/ (FastAPI)         frontend/ (React + Vite)
  ├─ 获取 API 数据              ├─ main.py /api/*          ├─ pages/DashboardPage
  ├─ 分析 / 信号逻辑            ├─ database.py SQLite      ├─ pages/FundDetailPage
  ├─ 发送通知                    ├─ auth.py 认证依赖       ├─ pages/LoginPage
  └─ 保存到 SQLite  ──────────►  └─ 提供 dist/ 静态文件    └─ components/FundCard, charts
```

**多用户架构**: 每个用户独立注册（用户名+密码），各自配置基金列表和月预算。`notify.py` 遍历所有用户，共享分析结果（同一基金只分析一次），按用户预算分别计算建议金额，通过各自的通知渠道推送。Web 面板需要登录，用户只看自己的数据。

**数据持久化**（`data/jijin.db`，SQLite）：`backend/database.py` 管理表（`funds`、`daily_snapshots`、`settings`、`users`、`user_funds`、`user_settings`、`user_tokens`）。`notify.py` 每次运行后调用 `save_run_results()`。FastAPI 后端读取同一数据库。两者共用 `backend/database.py`。

**月预算流转**: `MONTHLY_INVEST_BUDGET` 环境变量 → SQLite `settings.monthly_budget`（通过 Web 面板 `PUT /api/investment-plan` 设置）。`notify.py` 的 `get_monthly_budget_setting()` 先检查环境变量，再回退到 SQLite。

**基金配置**（`WATCH_FUNDS` 在 `notify.py` 中，是唯一权威列表）:
- ETF 使用 K 线数据；场外基金使用净值数据
- 股息率数据源优先级：`yield_etf`（ETF 分红历史）> `index_name`（蛋卷指数估值）
- `index_code` 提供中证指数 PE，作为股息率数据不可用时的回退估值来源
- **行为差异**: `yield_etf` 路径有 `hist_yield`（历史中位值），所以 `effective = yield_pct / hist_yield × 5.0` 是标准化后的值。`index_name` 路径没有 `hist_yield`，`effective` 等于原始 `yield_pct`，直接与 6/8 阈值比较的意义较弱。

**策略**（在 `analyze` 中）: `effective_yield = yield_pct / hist_yield × 5.0`。信号阈值：`>= 6.0` = 加倍定投（2x），`>= 8.0` = 大举买入（5x）。完整 0x–5x 倍率表见 `ARCHITECTURE.md`。

**外部 API**: eastmoney（分红、K 线、净值），sina（实时价格），danjuanfunds.com（指数估值），akshare（Python 库，K 线/中证指数的优先方案），企业微信 webhook，PushPlus。

## 部署

GitHub Actions（`.github/workflows/notify.yml`）在北京时间工作日 9:30（UTC 1:30）运行 `notify.py`。`WECOM_KEY` 存储在 GitHub Secrets 中。本地 cron 替代方案见 `scripts/install_cron.sh`。

## 约定

- 日期比较统一使用北京时间（`TZ_BEIJING`）
- 内存缓存（`_val_cache`、`_etf_yield_cache`、`_cni_cache`）避免单次运行内重复 API 调用
- `akshare` 导入是懒加载的（`get_akshare()`），导入失败时回退到 HTTP API
- ETF 市场前缀规则：代码以 `51`/`56` 开头 → `sh`，其他 → `sz`
- `.gitignore` 排除了 `opencode.json`（AI 配置）、`a.scpt`、`*.log` 和 `__pycache__`
