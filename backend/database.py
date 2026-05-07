"""SQLite persistence layer shared by notify.py and the FastAPI backend."""

import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from calendar import monthrange
import sys
from pathlib import Path

TZ_BEIJING = timezone(timedelta(hours=8))
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
DB_PATH = BASE_DIR / "data" / "jijin.db"
INVEST_STEP = 50

try:
    from notify import valuation_level, round_invest_amount, month_workdays
except ImportError:
    def valuation_level(effective):
        if effective is None:
            return ""
        if effective < 4.0:
            return "很贵"
        if effective < 5.0:
            return "偏贵"
        elif effective < 6.0:
            return "合理"
        elif effective < 7.0:
            return "略便宜"
        elif effective < 8.0:
            return "便宜"
        else:
            return "很便宜"

    def round_invest_amount(amount, step=INVEST_STEP):
        if amount is None or amount <= 0:
            return 0
        return max(step, int(round(amount / step)) * step)

    def month_workdays(day=None):
        day = day or _now_bj().date()
        _, days = monthrange(day.year, day.month)
        return sum(
            1
            for d in range(1, days + 1)
            if datetime(day.year, day.month, d).weekday() < 5
        )


def _now_bj():
    return datetime.now(tz=TZ_BEIJING)


@contextmanager
def _conn():
    """Yield a sqlite3 connection with WAL mode and foreign keys on."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db():
    """Create tables if they don't already exist. Idempotent."""
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS funds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'etf',
                market TEXT,
                yield_etf TEXT,
                index_name TEXT,
                index_code TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_id INTEGER NOT NULL REFERENCES funds(id),
                date TEXT NOT NULL,
                price REAL,
                yield_pct REAL,
                hist_yield REAL,
                effective_yield REAL,
                signal TEXT,
                valuation_level TEXT,
                pe REAL,
                pb REAL,
                ma20 REAL,
                ma60 REAL,
                price_deviation_pct REAL,
                dca_multiplier REAL,
                daily_base_amount INTEGER,
                suggested_amount INTEGER,
                UNIQUE(fund_id, date)
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_fund_date
                ON daily_snapshots(fund_id, date);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                wecom_key TEXT,
                pushplus_token TEXT,
                notify_type TEXT DEFAULT 'wecom',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_funds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'etf',
                market TEXT,
                yield_etf TEXT,
                index_name TEXT,
                index_code TEXT,
                UNIQUE(user_id, code)
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                monthly_budget INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
        """)
        _ensure_column(conn, "daily_snapshots", "daily_base_amount", "INTEGER")
        _ensure_column(conn, "daily_snapshots", "suggested_amount", "INTEGER")


def _ensure_column(conn, table, column, definition):
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def upsert_fund(fund_cfg):
    """Insert or update a fund row from a WATCH_FUNDS dict. Returns fund id."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM funds WHERE code = ?", (fund_cfg["code"],)
        ).fetchone()
        if row:
            fund_id = row["id"]
            conn.execute(
                """UPDATE funds SET name=?, type=?, market=?, yield_etf=?,
                   index_name=?, index_code=? WHERE id=?""",
                (
                    fund_cfg["name"],
                    fund_cfg.get("type", "etf"),
                    fund_cfg.get("market"),
                    fund_cfg.get("yield_etf"),
                    fund_cfg.get("index_name"),
                    fund_cfg.get("index_code"),
                    fund_id,
                ),
            )
        else:
            cur = conn.execute(
                """INSERT INTO funds (code, name, type, market, yield_etf,
                   index_name, index_code) VALUES (?,?,?,?,?,?,?)""",
                (
                    fund_cfg["code"],
                    fund_cfg["name"],
                    fund_cfg.get("type", "etf"),
                    fund_cfg.get("market"),
                    fund_cfg.get("yield_etf"),
                    fund_cfg.get("index_name"),
                    fund_cfg.get("index_code"),
                ),
            )
            fund_id = cur.lastrowid
    return fund_id


def insert_snapshot(fund_id, result):
    """Insert one daily snapshot from an analyze() / check_fund() result dict."""
    if "reason" in result:
        return  # skip error results (no data)

    valuation = result.get("valuation") or {}
    cni_data = result.get("cni_data") or {}

    pe = valuation.get("pe")
    if pe is None and cni_data.get("pe"):
        pe = cni_data["pe"]

    today = _now_bj().strftime("%Y-%m-%d")

    with _conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO daily_snapshots
               (fund_id, date, price, yield_pct, hist_yield, effective_yield,
                signal, valuation_level, pe, pb, ma20, ma60, price_deviation_pct,
                dca_multiplier, daily_base_amount, suggested_amount)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fund_id,
                today,
                result.get("current_price"),
                valuation.get("yield_pct"),
                valuation.get("hist_yield"),
                result.get("effective"),
                result.get("action"),
                valuation_level(result.get("effective")),
                pe,
                valuation.get("pb"),
                result.get("ma20"),
                result.get("ma60"),
                result.get("diff_pct"),
                result.get("dca_multiplier"),
                result.get("daily_base_amount"),
                result.get("suggested_amount"),
            ),
        )


def save_run_results(funds_config, results):
    """Called by notify.main() after notifications. Persists all results."""
    try:
        init_db()
        for fund_cfg in funds_config:
            fund_id = upsert_fund(fund_cfg)
            # find matching result by code
            for r in results:
                if r["code"] == fund_cfg["code"]:
                    insert_snapshot(fund_id, r)
                    break
        print("数据已写入 SQLite")
    except Exception as e:
        print(f"数据写入 SQLite 失败（不影响通知）: {e}")


# ── Query helpers for the FastAPI backend ──


def get_all_funds():
    with _conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM funds").fetchall()]


def get_fund(fund_id):
    with _conn() as conn:
        r = conn.execute("SELECT * FROM funds WHERE id = ?", (fund_id,)).fetchone()
    return dict(r) if r else None


def get_snapshots(fund_id, days=90):
    init_db()
    plan = get_investment_plan()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM daily_snapshots
               WHERE fund_id = ?
               ORDER BY date DESC
               LIMIT ?""",
            (fund_id, days),
        ).fetchall()
    result = []
    for row in reversed(rows):
        item = dict(row)
        if item.get("dca_multiplier") is not None and plan["daily_base_amount"]:
            item["daily_base_amount"] = plan["daily_base_amount"]
            item["suggested_amount"] = round_invest_amount(
                plan["daily_base_amount"] * item["dca_multiplier"]
            )
        result.append(item)
    return result


def get_dashboard():
    """Latest snapshot per fund, joined with fund info."""
    init_db()
    plan = get_investment_plan()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT f.id, f.name, f.code, f.type,
                      s.date, s.price, s.yield_pct, s.hist_yield,
                      s.effective_yield, s.signal, s.valuation_level,
                      s.pe, s.pb, s.ma20, s.ma60, s.price_deviation_pct,
                      s.dca_multiplier, s.daily_base_amount, s.suggested_amount
               FROM funds f
               LEFT JOIN daily_snapshots s ON s.fund_id = f.id
               AND s.date = (SELECT MAX(date) FROM daily_snapshots WHERE fund_id = f.id)
               ORDER BY f.id"""
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        if item.get("dca_multiplier") is not None and plan["daily_base_amount"]:
            item["daily_base_amount"] = plan["daily_base_amount"]
            item["suggested_amount"] = round_invest_amount(
                plan["daily_base_amount"] * item["dca_multiplier"]
            )
        result.append(item)
    return result




def get_monthly_budget():
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'monthly_budget'"
        ).fetchone()
    if not row:
        return 0
    try:
        return int(float(row["value"]))
    except (TypeError, ValueError):
        return 0


def set_monthly_budget(amount):
    init_db()
    amount = max(0, int(float(amount or 0)))
    with _conn() as conn:
        conn.execute(
            """INSERT INTO settings (key, value, updated_at)
               VALUES ('monthly_budget', ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                 value = excluded.value,
                 updated_at = excluded.updated_at""",
            (str(amount), _now_bj().isoformat()),
        )
    return get_investment_plan()


def get_investment_plan():
    monthly_budget = get_monthly_budget()
    workdays = month_workdays()
    daily_raw = monthly_budget / workdays if monthly_budget and workdays else 0
    return {
        "monthly_budget": monthly_budget,
        "workdays": workdays,
        "daily_base_amount": round_invest_amount(daily_raw),
        "round_step": INVEST_STEP,
    }


# ── User management ──


def _hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return salt + ":" + dk.hex()


def _verify_password(password, password_hash):
    salt, stored_hash = password_hash.split(":", 1)
    return _hash_password(password, salt) == password_hash


def register_user(username, password):
    init_db()
    if not username or not password:
        return None
    pw_hash = _hash_password(password)
    now = _now_bj().isoformat()
    try:
        with _conn() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
                (username, pw_hash, now),
            )
            user_id = cur.lastrowid
            conn.execute(
                "INSERT INTO user_settings (user_id, monthly_budget, updated_at) VALUES (?,5000,?)",
                (user_id, now),
            )
    except sqlite3.IntegrityError:
        return None
    return {"id": user_id, "username": username}


def authenticate_user(username, password):
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"]}


def create_user_token(user_id):
    init_db()
    token = secrets.token_hex(32)
    now = _now_bj().isoformat()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO user_tokens (user_id, token, created_at) VALUES (?,?,?)",
            (user_id, token, now),
        )
        # 每个用户最多保留最近 10 个有效 token
        conn.execute(
            """DELETE FROM user_tokens WHERE id NOT IN (
                   SELECT id FROM user_tokens WHERE user_id = ?
                   ORDER BY created_at DESC LIMIT 10
               ) AND user_id = ?""",
            (user_id, user_id),
        )
    return token


def delete_user_token(token):
    init_db()
    with _conn() as conn:
        conn.execute("DELETE FROM user_tokens WHERE token = ?", (token,))


def get_user_by_token(token):
    init_db()
    # 超过 30 天的 token 自动失效
    cutoff = (_now_bj() - timedelta(days=30)).isoformat()
    with _conn() as conn:
        row = conn.execute(
            "SELECT u.id, u.username, u.wecom_key, u.pushplus_token, u.notify_type "
            "FROM user_tokens t JOIN users u ON u.id = t.user_id "
            "WHERE t.token = ? AND t.created_at > ?",
            (token, cutoff),
        ).fetchone()
    return dict(row) if row else None


# ── Per-user fund CRUD ──


def get_user_funds(user_id):
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM user_funds WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_user_fund(user_id, fund_cfg):
    init_db()
    try:
        with _conn() as conn:
            cur = conn.execute(
                """INSERT INTO user_funds (user_id, code, name, type, market, yield_etf, index_name, index_code)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    user_id,
                    fund_cfg["code"],
                    fund_cfg["name"],
                    fund_cfg.get("type", "etf"),
                    fund_cfg.get("market"),
                    fund_cfg.get("yield_etf"),
                    fund_cfg.get("index_name"),
                    fund_cfg.get("index_code"),
                ),
            )
            return {"id": cur.lastrowid, **fund_cfg}
    except sqlite3.IntegrityError:
        return None


def update_user_fund(user_id, fund_id, fund_cfg):
    with _conn() as conn:
        conn.execute(
            """UPDATE user_funds SET code=?, name=?, type=?, market=?, yield_etf=?, index_name=?, index_code=?
               WHERE id=? AND user_id=?""",
            (
                fund_cfg["code"],
                fund_cfg["name"],
                fund_cfg.get("type", "etf"),
                fund_cfg.get("market"),
                fund_cfg.get("yield_etf"),
                fund_cfg.get("index_name"),
                fund_cfg.get("index_code"),
                fund_id,
                user_id,
            ),
        )
    return {"id": fund_id, **fund_cfg}


def delete_user_fund(user_id, fund_id):
    with _conn() as conn:
        conn.execute(
            "DELETE FROM user_funds WHERE id=? AND user_id=?",
            (fund_id, user_id),
        )


# ── Per-user settings ──


def get_user_monthly_budget(user_id):
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT monthly_budget FROM user_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return 0
    try:
        return int(float(row["monthly_budget"]))
    except (TypeError, ValueError):
        return 0


def set_user_monthly_budget(user_id, amount):
    init_db()
    amount = max(0, int(float(amount or 0)))
    now = _now_bj().isoformat()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO user_settings (user_id, monthly_budget, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 monthly_budget = excluded.monthly_budget,
                 updated_at = excluded.updated_at""",
            (user_id, str(amount), now),
        )


def get_user_investment_plan(user_id):
    monthly_budget = get_user_monthly_budget(user_id)
    workdays = month_workdays()
    daily_raw = monthly_budget / workdays if monthly_budget and workdays else 0
    return {
        "monthly_budget": monthly_budget,
        "workdays": workdays,
        "daily_base_amount": round_invest_amount(daily_raw),
        "round_step": INVEST_STEP,
    }


def get_user_dashboard(user_id):
    """Latest snapshot per fund joined with user_funds, filtered to user's fund list."""
    init_db()
    plan = get_user_investment_plan(user_id)
    with _conn() as conn:
        rows = conn.execute(
            """SELECT f.id, f.name, f.code, f.type,
                       s.date, s.price, s.yield_pct, s.hist_yield,
                       s.effective_yield, s.signal, s.valuation_level,
                       s.pe, s.pb, s.ma20, s.ma60, s.price_deviation_pct,
                       s.dca_multiplier, s.daily_base_amount, s.suggested_amount
               FROM user_funds f
               LEFT JOIN daily_snapshots s ON s.fund_id = (
                   SELECT f2.id FROM funds f2 WHERE f2.code = f.code
               )
               AND s.date = (
                   SELECT MAX(date) FROM daily_snapshots
                   WHERE fund_id = (SELECT f3.id FROM funds f3 WHERE f3.code = f.code)
               )
               WHERE f.user_id = ?
               ORDER BY f.id""",
            (user_id,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        if item.get("dca_multiplier") is not None and plan["daily_base_amount"]:
            item["daily_base_amount"] = plan["daily_base_amount"]
            item["suggested_amount"] = round_invest_amount(
                plan["daily_base_amount"] * item["dca_multiplier"]
            )
        result.append(item)
    return result


def get_user_fund_detail(user_id, fund_id):
    """Get one user_fund row with latest snapshot."""
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_funds WHERE id = ? AND user_id = ?",
            (fund_id, user_id),
        ).fetchone()
    if not row:
        return None
    fund = dict(row)
    with _conn() as conn:
        snap = conn.execute(
            """SELECT * FROM daily_snapshots
               WHERE fund_id = (SELECT id FROM funds WHERE code = ?)
               ORDER BY date DESC LIMIT 1""",
            (fund["code"],),
        ).fetchone()
    if snap:
        fund["latest_snapshot"] = dict(snap)
    return fund


def get_user_fund_snapshots(user_id, fund_id, days=90):
    """Get snapshots for a user's fund by code, with per-user budget applied."""
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT code FROM user_funds WHERE id = ? AND user_id = ?",
            (fund_id, user_id),
        ).fetchone()
    if not row:
        return []
    code = row["code"]
    plan = get_user_investment_plan(user_id)
    with _conn() as conn:
        fund_row = conn.execute(
            "SELECT id FROM funds WHERE code = ?", (code,)
        ).fetchone()
    if not fund_row:
        return []
    global_fund_id = fund_row["id"]
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM daily_snapshots
               WHERE fund_id = ?
               ORDER BY date DESC
               LIMIT ?""",
            (global_fund_id, days),
        ).fetchall()
    result = []
    for row in reversed(rows):
        item = dict(row)
        if item.get("dca_multiplier") is not None and plan["daily_base_amount"]:
            item["daily_base_amount"] = plan["daily_base_amount"]
            item["suggested_amount"] = round_invest_amount(
                plan["daily_base_amount"] * item["dca_multiplier"]
            )
        result.append(item)
    return result


# ── Notify: get all users and their fund configs ──


def get_all_users_with_funds():
    """Return list of {user: {...}, funds: [...], budget: int} for notify.py."""
    init_db()
    with _conn() as conn:
        users = conn.execute("SELECT * FROM users").fetchall()
    result = []
    for u in users:
        user = dict(u)
        with _conn() as conn:
            fund_rows = conn.execute(
                "SELECT * FROM user_funds WHERE user_id = ? ORDER BY id",
                (user["id"],),
            ).fetchall()
        funds = [dict(r) for r in fund_rows]
        budget = get_user_monthly_budget(user["id"])
        result.append({
            "user": user,
            "funds": funds,
            "monthly_budget": budget,
        })
    return result
