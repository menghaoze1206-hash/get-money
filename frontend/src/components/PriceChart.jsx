import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

export default function PriceChart({ snapshots }) {
  if (!snapshots || snapshots.length === 0) {
    return <p className="chart-empty">暂无数据</p>;
  }

  const data = snapshots.map((s) => ({
    date: s.date,
    price: s.price,
    ma20: s.ma20,
    ma60: s.ma60,
  }));

  return (
    <div className="chart-container">
      <h3>价格 & 均线</h3>
      <ResponsiveContainer width="100%" height={350}>
        <LineChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="price" stroke="#2563eb" strokeWidth={2} dot={false} name="价格" />
          <Line type="monotone" dataKey="ma20" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="MA20" />
          <Line type="monotone" dataKey="ma60" stroke="#10b981" strokeWidth={1.5} dot={false} name="MA60" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
