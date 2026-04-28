# 优化记录

## 后端 `server.py`

### 优化1: POST 添加基金时重复请求上游（高）
- **现状**: `do_POST /api/watchlist` 中调用 `fetch_estimate()` 校验代码，成功后前端 `addFund()` 又调用 `refreshAll()` 再次请求同一基金。
- **方案**: POST 成功后直接返回该基金的估值数据给前端，前端不再触发完整 `refreshAll()`。

### 优化2: watchlist 频繁读写文件（中）
- **现状**: 每次 GET/POST/DELETE 都 `load_watchlist()` + `save_watchlist()` 读写 JSON 文件。
- **方案**: 在内存中缓存 watchlist，写操作同时更新内存和文件，读操作直接返回内存数据。

### 优化3: 静态文件无缓存头（中）
- **现状**: JS/CSS 每次请求都全量返回，无 `Cache-Control` / `ETag`。
- **方案**: 添加 `Cache-Control: public, max-age=3600` 缓存头，对带 hash 的文件设置更长缓存。

### 优化4: `do_HEAD` 和 `serve_static` 代码重复（低）
- **现状**: 两处有相同的路径安全校验和文件存在性检查逻辑。
- **方案**: 提取共用方法 `_resolve_static_path()`。

## 前端 `app.js`

### 优化5: `renderCards()` 每次全量替换 innerHTML（中）
- **现状**: 每次刷新都重建全部 DOM（含 SVG 图表字符串），基金多时性能抖动。
- **方案**: 改为差异更新 —— 只更新变化卡片的动态数据（价格、涨跌、图表），不重建整个 DOM。

### 优化6: 刷新请求无防抖（高）
- **现状**: 用户快速点击"立即刷新"会触发多个并发的 `refreshAll()`。
- **方案**: 添加防抖锁，上一次刷新未完成时忽略新的刷新请求。

### 优化7: `parseTradingMinute` 正则每次重新创建（低）
- **现状**: `/(\d{2}):(\d{2})/` 每次函数调用都新建。
- **方案**: 提升到模块顶层常量。

### 优化8: `toFixed` 二次格式转换（低）
- **现状**: `renderCards` 中先 `.toFixed(4)` 再传给 `formatSignedValue`，后者又 `Number()` 一次。
- **方案**: 直接传数字，去掉多余的 `.toFixed()` 调用。

## CSS `styles.css`

### 优化9: 硬编码颜色未用 CSS 变量（低）
- **现状**: `#fff1f2`、`#be123c`、`#e1e9f6`、`#f8fbff` 等散落各处。
- **方案**: 统一为 CSS 变量，便于主题切换。
