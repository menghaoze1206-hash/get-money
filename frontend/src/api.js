const BASE = '/api';

function authHeaders() {
  const token = localStorage.getItem('token');
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export async function getFunds() {
  const res = await fetch(`${BASE}/funds`);
  return res.json();
}

export async function getFund(id) {
  const res = await fetch(`${BASE}/funds/${id}`);
  return res.json();
}

export async function getSnapshots(id, days = 90) {
  const res = await fetch(`${BASE}/funds/${id}/snapshots?days=${days}`);
  return res.json();
}

export async function getDashboard() {
  const res = await fetch(`${BASE}/dashboard`);
  return res.json();
}

export async function getInvestmentPlan() {
  const res = await fetch(`${BASE}/investment-plan`);
  return res.json();
}

export async function updateInvestmentPlan(monthlyBudget) {
  const res = await fetch(`${BASE}/investment-plan`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ monthly_budget: monthlyBudget }),
  });
  return res.json();
}

// ── Auth ──

export async function login(username, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || '登录失败');
  }
  return res.json();
}

export async function register(username, password) {
  const res = await fetch(`${BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || '注册失败');
  }
  return res.json();
}

export async function getMe() {
  const res = await fetch(`${BASE}/auth/me`, { headers: authHeaders() });
  if (!res.ok) return null;
  return res.json();
}

export async function logout() {
  await fetch(`${BASE}/auth/logout`, {
    method: 'POST',
    headers: authHeaders(),
  }).catch(() => {});
}

// ── User-scoped fund CRUD ──

export async function getUserFunds() {
  const res = await fetch(`${BASE}/user/funds`, { headers: authHeaders() });
  return res.json();
}

export async function addUserFund(fund) {
  const res = await fetch(`${BASE}/user/funds`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(fund),
  });
  if (!res.ok) throw new Error('添加基金失败');
  return res.json();
}

export async function updateUserFund(id, fund) {
  const res = await fetch(`${BASE}/user/funds/${id}`, {
    method: 'PUT',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(fund),
  });
  if (!res.ok) throw new Error('更新基金失败');
  return res.json();
}

export async function deleteUserFund(id) {
  const res = await fetch(`${BASE}/user/funds/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  return res.json();
}

// ── User-scoped dashboard / plan ──

export async function getUserDashboard() {
  const res = await fetch(`${BASE}/user/dashboard`, { headers: authHeaders() });
  return res.json();
}

export async function getUserInvestmentPlan() {
  const res = await fetch(`${BASE}/user/investment-plan`, { headers: authHeaders() });
  return res.json();
}

export async function updateUserInvestmentPlan(monthlyBudget) {
  const res = await fetch(`${BASE}/user/investment-plan`, {
    method: 'PUT',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ monthly_budget: monthlyBudget }),
  });
  return res.json();
}

export async function getUserFundDetail(id) {
  const res = await fetch(`${BASE}/user/funds/${id}/detail`, { headers: authHeaders() });
  return res.json();
}

export async function getUserFundSnapshots(id, days = 90) {
  const res = await fetch(`${BASE}/user/funds/${id}/snapshots?days=${days}`, { headers: authHeaders() });
  return res.json();
}
