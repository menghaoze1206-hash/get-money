import { useEffect, useState } from 'react';
import {
  getUserDashboard,
  getUserInvestmentPlan,
  updateUserInvestmentPlan,
  getUserFunds,
  addUserFund,
  deleteUserFund,
  updateUserFund,
} from '../api';
import FundCard from '../components/FundCard';

const PRESET_FUNDS = [
  { name: '红利低波ETF', code: '512890', market: '1', index_name: '红利低波' },
  { name: '自由现金流ETF', code: '159201', market: '0', yield_etf: '159201', index_code: '980092' },
  { name: '南方红利低波联接A', code: '008163', type: 'fund', index_name: '标普红利' },
];

export default function DashboardPage() {
  const [funds, setFunds] = useState([]);
  const [userFunds, setUserFunds] = useState([]);
  const [plan, setPlan] = useState(null);
  const [budgetInput, setBudgetInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [showEdit, setShowEdit] = useState(null);
  const [editForm, setEditForm] = useState({});
  const hasBudget = Boolean(plan?.monthly_budget);

  function load() {
    Promise.all([getUserDashboard(), getUserInvestmentPlan(), getUserFunds()])
      .then(([dashboard, investmentPlan, uf]) => {
        setFunds(dashboard);
        setPlan(investmentPlan);
        setUserFunds(uf);
        setBudgetInput(
          investmentPlan.monthly_budget ? String(investmentPlan.monthly_budget) : ''
        );
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  function handleBudgetSubmit(e) {
    e.preventDefault();
    const value = Number(budgetInput);
    if (!Number.isFinite(value) || value < 0) return;
    setSaving(true);
    updateUserInvestmentPlan(Math.round(value))
      .then((nextPlan) => {
        setPlan(nextPlan);
        return getUserDashboard();
      })
      .then(setFunds)
      .catch(console.error)
      .finally(() => setSaving(false));
  }

  function handleAddPreset(preset) {
    addUserFund(preset)
      .then(() => {
        setShowAdd(false);
        return Promise.all([getUserDashboard(), getUserFunds()]);
      })
      .then(([d, uf]) => { setFunds(d); setUserFunds(uf); })
      .catch(console.error);
  }

  function handleDelete(fundId) {
    if (!confirm('确定删除该基金？')) return;
    deleteUserFund(fundId)
      .then(() => Promise.all([getUserDashboard(), getUserFunds()]))
      .then(([d, uf]) => { setFunds(d); setUserFunds(uf); })
      .catch(console.error);
  }

  function openEdit(fund) {
    setShowEdit(fund.id);
    setEditForm({ ...fund });
  }

  function handleEditSubmit(e) {
    e.preventDefault();
    updateUserFund(showEdit, editForm)
      .then(() => {
        setShowEdit(null);
        return Promise.all([getUserDashboard(), getUserFunds()]);
      })
      .then(([d, uf]) => { setFunds(d); setUserFunds(uf); })
      .catch(console.error);
  }

  function handleCustomAdd(e) {
    e.preventDefault();
    const form = editForm;
    if (!form.code || !form.name) return;
    addUserFund({
      code: form.code,
      name: form.name,
      type: form.type || 'etf',
      market: form.market || '',
      yield_etf: form.yield_etf || '',
      index_name: form.index_name || '',
      index_code: form.index_code || '',
    })
      .then(() => {
        setShowAdd(false);
        setEditForm({});
        return Promise.all([getUserDashboard(), getUserFunds()]);
      })
      .then(([d, uf]) => { setFunds(d); setUserFunds(uf); })
      .catch(console.error);
  }

  if (loading) return <p className="page-status">加载中...</p>;

  return (
    <div>
      <section className="budget-panel">
        <div>
          <h2>月投入预算</h2>
          <p>
            {plan?.monthly_budget
              ? `本月约 ${plan.workdays} 个交易日，基础日投 ${plan.daily_base_amount} 元`
              : '输入每月可投入资金后，系统会按交易日拆成易执行的整数金额'}
          </p>
        </div>
        <form className="budget-form" onSubmit={handleBudgetSubmit}>
          <label htmlFor="monthly-budget">每月资金</label>
          <input
            id="monthly-budget"
            inputMode="numeric"
            min="0"
            step="50"
            type="number"
            value={budgetInput}
            onChange={(e) => setBudgetInput(e.target.value)}
            placeholder="5000"
          />
          <button type="submit" disabled={saving}>
            {saving ? '保存中' : hasBudget ? '修改' : '保存'}
          </button>
        </form>
      </section>

      <section className="fund-manage">
        <div className="fund-manage-header">
          <h2>我的基金</h2>
          <button className="btn-add" onClick={() => { setShowAdd(!showAdd); setEditForm({}); }}>
            {showAdd ? '取消' : '+ 添加基金'}
          </button>
        </div>

        {showAdd && (
          <div className="fund-add-panel">
            <h3>预设基金（一键添加）</h3>
            <div className="preset-list">
              {PRESET_FUNDS.filter(p => !userFunds.some(uf => uf.code === p.code)).map((p) => (
                <button key={p.code} className="preset-btn" onClick={() => handleAddPreset(p)}>
                  {p.name} ({p.code})
                </button>
              ))}
            </div>
            <h3>自定义添加</h3>
            <form className="fund-edit-form" onSubmit={handleCustomAdd}>
              <input placeholder="基金代码 *" value={editForm.code || ''} onChange={e => setEditForm({ ...editForm, code: e.target.value })} />
              <input placeholder="基金名称 *" value={editForm.name || ''} onChange={e => setEditForm({ ...editForm, name: e.target.value })} />
              <select value={editForm.type || 'etf'} onChange={e => setEditForm({ ...editForm, type: e.target.value })}>
                <option value="etf">ETF</option>
                <option value="fund">场外基金</option>
              </select>
              <input placeholder="yield_etf" value={editForm.yield_etf || ''} onChange={e => setEditForm({ ...editForm, yield_etf: e.target.value })} />
              <input placeholder="index_name" value={editForm.index_name || ''} onChange={e => setEditForm({ ...editForm, index_name: e.target.value })} />
              <input placeholder="index_code" value={editForm.index_code || ''} onChange={e => setEditForm({ ...editForm, index_code: e.target.value })} />
              <button type="submit">添加</button>
            </form>
          </div>
        )}
      </section>

      {showEdit && (
        <div className="modal-overlay" onClick={() => setShowEdit(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h3>编辑基金</h3>
            <form className="fund-edit-form" onSubmit={handleEditSubmit}>
              <label>代码</label>
              <input value={editForm.code || ''} onChange={e => setEditForm({ ...editForm, code: e.target.value })} />
              <label>名称</label>
              <input value={editForm.name || ''} onChange={e => setEditForm({ ...editForm, name: e.target.value })} />
              <label>类型</label>
              <select value={editForm.type || 'etf'} onChange={e => setEditForm({ ...editForm, type: e.target.value })}>
                <option value="etf">ETF</option>
                <option value="fund">场外基金</option>
              </select>
              <label>yield_etf</label>
              <input value={editForm.yield_etf || ''} onChange={e => setEditForm({ ...editForm, yield_etf: e.target.value })} />
              <label>index_name</label>
              <input value={editForm.index_name || ''} onChange={e => setEditForm({ ...editForm, index_name: e.target.value })} />
              <label>index_code</label>
              <input value={editForm.index_code || ''} onChange={e => setEditForm({ ...editForm, index_code: e.target.value })} />
              <button type="submit">保存</button>
              <button type="button" className="btn-cancel" onClick={() => setShowEdit(null)}>取消</button>
            </form>
          </div>
        </div>
      )}

      <div className="fund-grid">
        {funds.map((f) => (
          <div key={f.id} style={{ position: 'relative' }}>
            <FundCard fund={f} />
            <button className="btn-edit-card" onClick={() => openEdit(f)} title="编辑">✎</button>
            <button className="btn-del-card" onClick={() => handleDelete(f.id)} title="删除">×</button>
          </div>
        ))}
        {funds.length === 0 && (
          <p className="page-status">暂无数据，请点击「添加基金」开始</p>
        )}
      </div>
    </div>
  );
}
