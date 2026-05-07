"""FastAPI backend for the dividend-yield timing dashboard."""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.database import (
    get_all_funds,
    get_fund,
    get_snapshots,
    get_dashboard,
    get_investment_plan,
    set_monthly_budget,
    register_user,
    authenticate_user,
    create_user_token,
    delete_user_token,
    get_user_funds,
    add_user_fund,
    update_user_fund,
    delete_user_fund,
    get_user_monthly_budget,
    set_user_monthly_budget,
    get_user_investment_plan,
    get_user_dashboard,
    get_user_fund_detail,
    get_user_fund_snapshots,
)

app = FastAPI(title="股息率择时信号", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth endpoints ──


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class FundConfig(BaseModel):
    code: str
    name: str
    type: str = "etf"
    market: Optional[str] = None
    yield_etf: Optional[str] = None
    index_name: Optional[str] = None
    index_code: Optional[str] = None


class MonthlyBudgetRequest(BaseModel):
    monthly_budget: int


@app.post("/api/auth/register")
def api_register(req: RegisterRequest):
    user = register_user(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    token = create_user_token(user["id"])
    return {"token": token, "user": user}


@app.post("/api/auth/login")
def api_login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_user_token(user["id"])
    return {"token": token, "user": user}


@app.get("/api/auth/me")
def api_me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"]}


@app.post("/api/auth/logout")
def api_logout(authorization: str = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        delete_user_token(authorization[len("Bearer "):])
    return {"ok": True}


# ── User-scoped fund CRUD ──


@app.get("/api/user/funds")
def api_user_funds(user: dict = Depends(get_current_user)):
    return get_user_funds(user["id"])


@app.post("/api/user/funds")
def api_add_user_fund(fund: FundConfig, user: dict = Depends(get_current_user)):
    result = add_user_fund(user["id"], fund.model_dump())
    if result is None:
        raise HTTPException(status_code=409, detail="该基金代码已存在")
    return result


@app.put("/api/user/funds/{fund_id}")
def api_update_user_fund(fund_id: int, fund: FundConfig, user: dict = Depends(get_current_user)):
    return update_user_fund(user["id"], fund_id, fund.model_dump())


@app.delete("/api/user/funds/{fund_id}")
def api_delete_user_fund(fund_id: int, user: dict = Depends(get_current_user)):
    delete_user_fund(user["id"], fund_id)
    return {"ok": True}


# ── User-scoped investment plan ──


@app.get("/api/user/investment-plan")
def api_user_investment_plan(user: dict = Depends(get_current_user)):
    return get_user_investment_plan(user["id"])


@app.put("/api/user/investment-plan")
def api_update_user_investment_plan(req: MonthlyBudgetRequest, user: dict = Depends(get_current_user)):
    set_user_monthly_budget(user["id"], req.monthly_budget)
    return get_user_investment_plan(user["id"])


# ── User-scoped dashboard & detail ──


@app.get("/api/user/dashboard")
def api_user_dashboard(user: dict = Depends(get_current_user)):
    return get_user_dashboard(user["id"])


@app.get("/api/user/funds/{fund_id}/detail")
def api_user_fund_detail(fund_id: int, user: dict = Depends(get_current_user)):
    detail = get_user_fund_detail(user["id"], fund_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="基金不存在")
    return detail


@app.get("/api/user/funds/{fund_id}/snapshots")
def api_user_fund_snapshots(
    fund_id: int,
    days: int = Query(90, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    return get_user_fund_snapshots(user["id"], fund_id, days)


# ── Legacy /api/* endpoints (keep for backwards compat) ──


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/funds")
def list_funds():
    return get_all_funds()


@app.get("/api/funds/{fund_id}")
def fund_detail(fund_id: int):
    return get_fund(fund_id)


@app.get("/api/funds/{fund_id}/snapshots")
def fund_snapshots(fund_id: int, days: int = Query(90, ge=1, le=365)):
    return get_snapshots(fund_id, days)


@app.get("/api/dashboard")
def dashboard():
    return get_dashboard()


@app.get("/api/investment-plan")
def investment_plan():
    return get_investment_plan()


class InvestmentSettings(BaseModel):
    monthly_budget: int


@app.put("/api/investment-plan")
def update_investment_plan(settings: InvestmentSettings):
    return set_monthly_budget(settings.monthly_budget)


# ── Static files (production: serve built frontend) ──

STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/favicon.svg")
    async def _favicon():
        return FileResponse(STATIC_DIR / "favicon.svg")

    @app.get("/icons.svg")
    async def _icons():
        return FileResponse(STATIC_DIR / "icons.svg")

    @app.get("/")
    async def _root():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Serve index.html for client-side routing paths like /login, /fund/123
        file_path = STATIC_DIR / full_path
        if file_path.exists():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")


def main():
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
