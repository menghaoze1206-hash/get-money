const state = {
  watchlist: [],
  timer: null,
  history: loadHistory(),
};

const cardsEl = document.querySelector("#cards");
const messageEl = document.querySelector("#message");
const updatedAtEl = document.querySelector("#updated-at");
const marketStatusEl = document.querySelector("#market-status");
const addForm = document.querySelector("#add-form");
const refreshBtn = document.querySelector("#refresh-btn");
const HISTORY_STORAGE_KEY = "fund-value-history-v1";
const CHART_WIDTH = 320;
const CHART_HEIGHT = 132;
const TRADING_MINUTES = 240;
const TRADING_AXIS_LABELS = [
  { label: "09:30", minute: 0 },
  { label: "11:30", minute: 120 },
  { label: "13:00", minute: 120 },
  { label: "15:00", minute: 240 },
];

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveHistory() {
  localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(state.history));
}

function getHistoryDateKey(item) {
  return item.gztime ? String(item.gztime).slice(0, 10) : new Date().toISOString().slice(0, 10);
}

function getHistoryBucket(code, dateKey) {
  if (!state.history[code] || state.history[code].date !== dateKey) {
    state.history[code] = { date: dateKey, points: [] };
  }
  return state.history[code];
}

function pruneHistory() {
  const activeCodes = new Set(state.watchlist.map((item) => item.code));
  for (const code of Object.keys(state.history)) {
    if (!activeCodes.has(code)) {
      delete state.history[code];
    }
  }
  saveHistory();
}

function showMessage(text) {
  if (!text) {
    messageEl.hidden = true;
    messageEl.textContent = "";
    return;
  }
  messageEl.hidden = false;
  messageEl.textContent = text;
}

function isMarketOpen(now = new Date()) {
  const day = now.getDay();
  if (day === 0 || day === 6) return false;
  const minutes = now.getHours() * 60 + now.getMinutes();
  const morning = minutes >= 9 * 60 + 30 && minutes <= 11 * 60 + 30;
  const afternoon = minutes >= 13 * 60 && minutes <= 15 * 60;
  return morning || afternoon;
}

function getRefreshInterval(now = new Date()) {
  return isMarketOpen(now) ? 20 * 1000 : 5 * 60 * 1000;
}

function formatSignedPercent(value) {
  const numeric = Number(value || 0);
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${numeric.toFixed(2)}%`;
}

function formatSignedValue(value) {
  const numeric = Number(value || 0);
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${numeric.toFixed(4)}`;
}

function formatTimeLabel(value) {
  if (!value) return "--";
  const pieces = String(value).split(" ");
  return pieces[1] || pieces[0] || "--";
}

function parseTradingMinute(value) {
  if (!value) return null;
  const timePart = formatTimeLabel(value);
  const match = /^(\d{2}):(\d{2})/.exec(timePart);
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  const total = hours * 60 + minutes;

  if (total < 570) return 0;
  if (total <= 690) return total - 570;
  if (total < 780) return 120;
  if (total <= 900) return 120 + (total - 780);
  return TRADING_MINUTES;
}

function getXAxisPosition(minute) {
  return (Math.max(0, Math.min(TRADING_MINUTES, minute)) / TRADING_MINUTES) * CHART_WIDTH;
}

function appendHistoryPoint(item) {
  if (!item || item.error || !item.code || !item.gsz) return;
  const dateKey = getHistoryDateKey(item);
  const bucket = getHistoryBucket(item.code, dateKey);
  const timestamp = item.gztime || new Date().toLocaleString("sv-SE").replace("T", " ");
  const numericValue = Number(item.gsz);
  const minute = parseTradingMinute(timestamp);
  if (!Number.isFinite(numericValue)) return;
  if (minute === null) return;

  const lastPoint = bucket.points[bucket.points.length - 1];
  if (lastPoint && lastPoint.t === timestamp) {
    lastPoint.v = numericValue;
    lastPoint.m = minute;
  } else {
    bucket.points.push({ t: timestamp, v: numericValue, m: minute });
  }

  if (bucket.points.length > 240) {
    bucket.points = bucket.points.slice(-240);
  }
}

function buildChart(item) {
  const bucket = state.history[item.code];
  const points = bucket?.points || [];
  if (points.length < 2) {
    return `
      <div class="chart-empty">
        <span>曲线会随着后续刷新逐步生成</span>
      </div>
    `;
  }

  const values = points.map((point) => point.v);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || Math.max(max * 0.002, 0.001);
  const polyline = points
    .map((point) => {
      const x = getXAxisPosition(point.m ?? 0);
      const y = CHART_HEIGHT - ((point.v - min) / range) * CHART_HEIGHT;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const firstPoint = points[0];
  const lastPoint = points[points.length - 1];
  const trendClass = Number(lastPoint.v - firstPoint.v) >= 0 ? "up" : "down";
  const axisLabels = TRADING_AXIS_LABELS.map(
    (tick) => `
      <span class="chart-tick" style="left:${((getXAxisPosition(tick.minute) / CHART_WIDTH) * 100).toFixed(2)}%">
        ${tick.label}
      </span>
    `
  ).join("");

  return `
    <div class="chart-panel">
      <div class="chart-header">
        <span>当日分时估值</span>
        <span class="${trendClass}">${formatSignedValue(lastPoint.v - firstPoint.v)}</span>
      </div>
      <svg class="chart" viewBox="0 0 ${CHART_WIDTH} ${CHART_HEIGHT}" preserveAspectRatio="none" aria-label="估值变化曲线">
        <line x1="0" y1="0.5" x2="${CHART_WIDTH}" y2="0.5" class="chart-grid" />
        <line x1="0" y1="${(CHART_HEIGHT / 2).toFixed(2)}" x2="${CHART_WIDTH}" y2="${(CHART_HEIGHT / 2).toFixed(2)}" class="chart-grid" />
        <line x1="0" y1="${(CHART_HEIGHT - 0.5).toFixed(2)}" x2="${CHART_WIDTH}" y2="${(CHART_HEIGHT - 0.5).toFixed(2)}" class="chart-grid" />
        <line x1="${getXAxisPosition(120).toFixed(2)}" y1="0" x2="${getXAxisPosition(120).toFixed(2)}" y2="${CHART_HEIGHT}" class="chart-grid chart-grid-session" />
        <polyline points="${polyline}" class="chart-line ${trendClass}" />
      </svg>
      <div class="chart-axis chart-axis-ticks">
        ${axisLabels}
      </div>
      <div class="chart-range">
        <span>低 ${min.toFixed(4)}</span>
        <span>最新 ${formatTimeLabel(lastPoint.t)}</span>
        <span>高 ${max.toFixed(4)}</span>
      </div>
    </div>
  `;
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

async function loadWatchlist() {
  const data = await request("/api/watchlist");
  state.watchlist = data.items || [];
  return state.watchlist;
}

async function fetchEstimate(code) {
  return request(`/api/estimate?code=${encodeURIComponent(code)}`);
}

function renderCards(items) {
  if (!items.length) {
    cardsEl.innerHTML = `<div class="card"><div class="card-header"><div><h2>还没有基金</h2><div class="card-code">先添加一个基金代码开始</div></div></div></div>`;
    return;
  }

  cardsEl.innerHTML = items
    .map((item) => {
      const changeClass = Number(item.gszzl || 0) >= 0 ? "up" : "down";
      return `
        <article class="card">
          <div class="card-header">
            <div>
              <h2>${item.name || item.code}</h2>
              <div class="card-code">${item.code}</div>
            </div>
            <div class="card-time">${item.gztime || "--"}</div>
          </div>
          <div class="price">${Number(item.gsz || 0).toFixed(4)}</div>
          <div class="delta ${changeClass}">${formatSignedPercent(item.gszzl)}</div>
          ${buildChart(item)}
          <div class="meta">
            <div class="meta-row">
              <span>上一日净值</span>
              <span>${Number(item.dwjz || 0).toFixed(4)}</span>
            </div>
            <div class="meta-row">
              <span>估算涨跌额</span>
              <span class="${changeClass}">${formatSignedValue((Number(item.gsz || 0) - Number(item.dwjz || 0)).toFixed(4))}</span>
            </div>
            <div class="meta-row">
              <span>当日单位净值日期</span>
              <span>${item.jzrq || "--"}</span>
            </div>
          </div>
          <div class="card-footer">
            <span class="subtle">估值仅供参考</span>
            <button class="delete-btn" data-code="${item.code}">删除</button>
          </div>
        </article>
      `;
    })
    .join("");
}

async function refreshAll() {
  showMessage("");
  marketStatusEl.textContent = isMarketOpen() ? "交易时段 · 20秒刷新" : "非交易时段 · 5分钟刷新";
  try {
    if (!state.watchlist.length) {
      await loadWatchlist();
    }
    const results = await Promise.all(
      state.watchlist.map(async (item) => {
        try {
          const estimate = await fetchEstimate(item.code);
          return { ...estimate, code: item.code };
        } catch (error) {
          return {
            code: item.code,
            name: item.name,
            gsz: 0,
            gszzl: 0,
            dwjz: 0,
            jzrq: "--",
            gztime: "--",
            error: error.message,
          };
        }
      })
    );
    results.forEach(appendHistoryPoint);
    saveHistory();
    renderCards(results);
    const now = new Date();
    updatedAtEl.textContent = `最近刷新：${now.toLocaleString("zh-CN")}`;
    const failed = results.filter((item) => item.error);
    if (failed.length) {
      showMessage(`有 ${failed.length} 只基金刷新失败，可能是上游接口临时不可用。`);
    }
  } catch (error) {
    showMessage(error.message);
    renderCards([]);
  }
}

async function addFund(code) {
  await request("/api/watchlist", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
  await loadWatchlist();
  await refreshAll();
}

async function removeFund(code) {
  await request(`/api/watchlist/${encodeURIComponent(code)}`, {
    method: "DELETE",
  });
  await loadWatchlist();
  delete state.history[code];
  saveHistory();
  await refreshAll();
}

function startPolling() {
  if (state.timer) {
    clearTimeout(state.timer);
  }
  const interval = getRefreshInterval();
  state.timer = setTimeout(async () => {
    await refreshAll();
    startPolling();
  }, interval);
}

addForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(addForm);
  const code = String(formData.get("code") || "").trim();
  if (!/^\d{6}$/.test(code)) {
    showMessage("请输入 6 位基金代码");
    return;
  }
  try {
    await addFund(code);
    addForm.reset();
  } catch (error) {
    showMessage(error.message);
  }
});

refreshBtn.addEventListener("click", () => {
  refreshAll();
});

cardsEl.addEventListener("click", async (event) => {
  const button = event.target.closest(".delete-btn");
  if (!button) return;
  try {
    await removeFund(button.dataset.code);
  } catch (error) {
    showMessage(error.message);
  }
});

async function bootstrap() {
  await loadWatchlist();
  pruneHistory();
  await refreshAll();
  startPolling();
}

bootstrap();
