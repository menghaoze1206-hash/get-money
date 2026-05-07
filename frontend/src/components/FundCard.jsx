import { Link } from 'react-router-dom';
import SignalBadge from './SignalBadge';

export default function FundCard({ fund }) {
  const hasData = fund.date != null;
  const mult = fund.dca_multiplier;

  return (
    <Link to={`/fund/${fund.id}`} className="fund-card">
      <h3 className="fund-card-name">
        {fund.name}
        <span className="fund-card-code">{fund.code}</span>
      </h3>

      {hasData ? (
        <div className="fund-card-body">
          <div className="fund-card-main">
            <span className="fund-card-yield">
              {fund.effective_yield != null ? fund.effective_yield.toFixed(1) : '--'}
            </span>
            <span className="fund-card-label">有效收益率</span>
            {mult != null && (
              <span className="fund-card-mult">{mult}x</span>
            )}
          </div>
          <div className="fund-card-meta">
            {fund.suggested_amount != null && (
              <span className="fund-card-amount">投 {fund.suggested_amount} 元</span>
            )}
            {fund.yield_pct != null && (
              <span>股息率 {fund.yield_pct}%</span>
            )}
            {fund.price != null && (
              <span>价格 {fund.price.toFixed(3)}</span>
            )}
            {fund.valuation_level && (
              <span>{fund.valuation_level}</span>
            )}
          </div>
          <SignalBadge signal={fund.signal} />
        </div>
      ) : (
        <p className="fund-card-empty">暂无数据</p>
      )}
    </Link>
  );
}
