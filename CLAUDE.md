# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A dividend-yield timing system: checks ETF/fund dividend yields on workdays, sends buy signals via WeChat (WeCom or PushPlus) when yields are cheap relative to history. **Does not use DCA (dollar-cost averaging) — only signals lump-sum buys at opportunistic moments.**

Read `ARCHITECTURE.md` for the full architecture, strategy formula, API dependencies, and evolution history.

## Commands

```bash
# Run once locally (uses env vars for WeCom key)
python3 notify.py

# Run via shell wrapper (sets WECOM_KEY, logs to data/notify.log)
./scripts/run.sh

# Quick test (checks env vars for current NOTIFY_TYPE)
./scripts/test.sh

# Install local cron (Mac, weekdays 9:30 Beijing time)
./scripts/install_cron.sh
```

There are no tests, no linter, and no build step. The project is a single Python 3 script (`notify.py`) with no dependencies beyond `akshare` (optional; falls back to HTTP APIs).

`scripts/run.sh` stores `WECOM_KEY` — replace the placeholder with your actual key. `a.scpt` in the repo root is a compiled AppleScript binary (Mac automation), now gitignored.

## Architecture

`notify.py` is the entire application (~700 lines). Entry point is `main()`.

**Flow**: `main()` → iterates `WATCH_FUNDS` → `check_fund()` → `analyze()` → `send_wecom()` or `send_pushplus()`

**Fund config** (`WATCH_FUNDS` at module level):
- ETFs use K-line data; field funds use NAV data
- Dividend yield source priority: `yield_etf` (ETF dividend history) > `index_name` (Danjuan index valuation)
- `index_code` provides CNI index PE as fallback when dividend data is unavailable
- **Behavioral difference**: `yield_etf` path produces `hist_yield` (historical median), so `effective = yield_pct / hist_yield × 5.0` is a normalized value. `index_name` path has no `hist_yield`, so `effective` equals raw `yield_pct` — direct comparison against the 6/8 thresholds is less meaningful in that case.

**Strategy** (in `analyze`): `effective_yield = yield_pct / hist_yield × 5.0`. Signal thresholds: `>= 6.0` = buy opportunity, `>= 8.0` = aggressive buy, `< 6.0` = keep waiting.

**Key functions** by concern:
- Data fetching: `fetch_etf_dividend_yield()`, `fetch_index_valuation()`, `fetch_kline()`, `fetch_fund_nav()`, `fetch_cni_index_data()`
- Signal logic: `calc_effective_yield()`, `calc_effective_from_pe()`, `buy_signal()`, `valuation_level()`, `analyze()`
- Notification: `send_wecom()`, `send_pushplus()`, `build_message()`

**External APIs**: eastmoney (dividends, K-line, NAV), sina (real-time prices), danjuanfunds.com (index valuation), akshare (Python lib, preferred for K-line/CNI), WeCom webhook, PushPlus.

## Deployment

GitHub Actions (`.github/workflows/notify.yml`) runs `notify.py` on weekdays at 9:30 AM Beijing time. `WECOM_KEY` is stored in GitHub Secrets. Local cron alternative available via `scripts/install_cron.sh`.

## Conventions

- Beijing time (`TZ_BEIJING`) used throughout for date comparisons
- In-memory caches (`_val_cache`, `_etf_yield_cache`, `_cni_cache`) avoid duplicate API calls within a single run
- `akshare` import is lazy (`get_akshare()`) — falls back to HTTP APIs on import failure
- ETF market prefix rule: codes starting with `51`/`56` → `sh`, others → `sz`
- `.gitignore` excludes `opencode.json` (AI config) and log files
