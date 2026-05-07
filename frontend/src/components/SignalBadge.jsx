const SIGNAL_STYLES = [
  { match: '大举买入', bg: '#fee2e2', color: '#dc2626' },
  { match: '加码', bg: '#ffedd5', color: '#ea580c' },
  { match: '加倍', bg: '#fff7ed', color: '#e67e22' },
  { match: '正常', bg: '#dcfce7', color: '#16a34a' },
  { match: '减少', bg: '#dbeafe', color: '#2563eb' },
  { match: '暂停', bg: '#f3f4f6', color: '#6b7280' },
];

export default function SignalBadge({ signal }) {
  const s = SIGNAL_STYLES.find((x) => signal && signal.includes(x.match)) || SIGNAL_STYLES[5];
  return (
    <span className="signal-badge" style={{ background: s.bg, color: s.color }}>
      {signal || '--'}
    </span>
  );
}
