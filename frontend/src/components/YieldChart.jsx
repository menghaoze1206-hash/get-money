import {
  ComposedChart,
  Line,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
} from 'recharts';

export default function YieldChart({ snapshots }) {
  if (!snapshots || snapshots.length === 0) {
    return <p className="chart-empty">暂无数据</p>;
  }

  const data = snapshots.map((s) => ({
    date: s.date,
    eff: s.effective_yield,
    yld: s.yield_pct,
    hist: s.hist_yield,
  }));

  const buySignals = snapshots
    .filter((s) => s.dca_multiplier != null && s.dca_multiplier >= 2)
    .map((s) => ({ date: s.date, eff: s.effective_yield }));

  return (
    <div className="chart-container">
      <h3>有效收益率 & 定投倍数阈值</h3>
      <ResponsiveContainer width="100%" height={350}>
        <ComposedChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <ReferenceLine y={8} stroke="#dc2626" strokeDasharray="5 5" label={{ value: '5x', position: 'right', fontSize: 11 }} />
          <ReferenceLine y={7} stroke="#f97316" strokeDasharray="4 4" label={{ value: '3x', position: 'right', fontSize: 11 }} />
          <ReferenceLine y={6} stroke="#e67e22" strokeDasharray="4 4" label={{ value: '2x', position: 'right', fontSize: 11 }} />
          <ReferenceLine y={5} stroke="#16a34a" strokeDasharray="3 3" label={{ value: '1x', position: 'right', fontSize: 11 }} />
          <ReferenceLine y={4} stroke="#94a3b8" strokeDasharray="3 3" label={{ value: '0.5x', position: 'right', fontSize: 11 }} />
          <Line type="monotone" dataKey="eff" stroke="#2563eb" strokeWidth={2} dot={false} name="有效收益率" />
          {buySignals.length > 0 && (
            <Scatter dataKey="eff" data={buySignals} fill="#dc2626" name="加码信号" />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
