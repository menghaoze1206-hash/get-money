import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getUserFundDetail, getUserFundSnapshots } from '../api';
import SignalBadge from '../components/SignalBadge';
import YieldChart from '../components/YieldChart';
import PriceChart from '../components/PriceChart';

export default function FundDetailPage() {
  const { id } = useParams();
  const [fund, setFund] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getUserFundDetail(id), getUserFundSnapshots(id)])
      .then(([f, s]) => {
        setFund(f);
        setSnapshots(s);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="page-status">加载中...</p>;
  if (!fund) return <p className="page-status">基金不存在</p>;

  return (
    <div>
      <Link to="/" className="back-link">&larr; 返回</Link>
      <div className="fund-detail-header">
        <h2>{fund.name}</h2>
        <span className="fund-card-code">{fund.code}</span>
        {snapshots.length > 0 && (
          <SignalBadge signal={snapshots[snapshots.length - 1].signal} />
        )}
      </div>

      {snapshots.length > 0 && (
        <div className="stats-row">
          <div className="stat">
            <span className="stat-value">
              {snapshots[snapshots.length - 1].effective_yield?.toFixed(1) ?? '--'}
            </span>
            <span className="stat-label">有效收益率</span>
          </div>
          <div className="stat">
            <span className="stat-value">
              {snapshots[snapshots.length - 1].yield_pct != null
                ? `${snapshots[snapshots.length - 1].yield_pct}%`
                : '--'}
            </span>
            <span className="stat-label">股息率</span>
          </div>
          <div className="stat">
            <span className="stat-value">
              {snapshots[snapshots.length - 1].price?.toFixed(3) ?? '--'}
            </span>
            <span className="stat-label">当前价格</span>
          </div>
          <div className="stat">
            <span className="stat-value">
              {snapshots[snapshots.length - 1].dca_multiplier != null
                ? `${snapshots[snapshots.length - 1].dca_multiplier}x`
                : '--'}
            </span>
            <span className="stat-label">定投倍数</span>
          </div>
          <div className="stat">
            <span className="stat-value">
              {snapshots[snapshots.length - 1].suggested_amount != null
                ? `${snapshots[snapshots.length - 1].suggested_amount}元`
                : '--'}
            </span>
            <span className="stat-label">建议投入</span>
          </div>
          <div className="stat">
            <span className="stat-value">
              {snapshots[snapshots.length - 1].valuation_level || '--'}
            </span>
            <span className="stat-label">估值水平</span>
          </div>
        </div>
      )}

      <YieldChart snapshots={snapshots} />
      <PriceChart snapshots={snapshots} />
    </div>
  );
}
