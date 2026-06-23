// Lightweight horizontal bar lists (no chart library needed) for the
// pre-computed analytics aggregates served by /api/analytics.

function BarList({ title, data, color = '#2563eb', unit = '' }) {
  const entries = Object.entries(data || {})
  const max = Math.max(1, ...entries.map(([, v]) => v))
  return (
    <div className="card analytics-block">
      <h4>{title}</h4>
      <div className="bars">
        {entries.map(([k, v]) => (
          <div className="bar-row" key={k}>
            <span className="bar-label" title={k}>{k.replace(/_/g, ' ')}</span>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${(v / max) * 100}%`, background: color }} />
            </div>
            <span className="bar-val">{v}{unit}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Analytics({ analytics }) {
  if (!analytics) return null
  return (
    <div className="analytics">
      <div className="stat-row">
        <Stat label="Total events" value={analytics.total_events} />
        <Stat label="Road-closure rate"
          value={`${Math.round((analytics.road_closure_rate || 0) * 100)}%`} />
        <Stat label="Corridors tracked"
          value={Object.keys(analytics.by_corridor || {}).length} />
        <Stat label="Junctions tracked"
          value={Object.keys(analytics.top_junctions || {}).length} />
      </div>
      <div className="analytics-grid">
        <BarList title="Events by cause" data={analytics.by_event_cause} color="#2563eb" />
        <BarList title="Busiest corridors" data={analytics.by_corridor} color="#0ea5e9" />
        <BarList title="Slowest-clearing corridors (median min)"
          data={analytics.corridor_median_clearance_min} color="#ef4444" unit="m" />
        <BarList title="Top junction hotspots" data={analytics.top_junctions} color="#8b5cf6" />
      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="card stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}
