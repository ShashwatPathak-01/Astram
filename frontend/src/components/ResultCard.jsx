const SEV_COLORS = {
  Low: '#10b981',
  Medium: '#f59e0b',
  High: '#f97316',
  Critical: '#ef4444',
}

// Shows the model forecast plus the recommended deployment plan.
export default function ResultCard({ result }) {
  if (!result) {
    return (
      <div className="card result placeholder">
        <p>Pick a location and submit an event to see the forecast and the
          recommended manpower / barricading / diversion plan.</p>
      </div>
    )
  }

  const color = SEV_COLORS[result.severity] || '#2563eb'
  const prob = Math.round((result.road_closure_probability || 0) * 100)

  return (
    <div className="card result">
      <div className="sev-banner" style={{ background: color }}>
        <span className="sev-label">{result.severity}</span>
        <span className="sev-score">{result.severity_score}/100</span>
      </div>

      <div className="metrics">
        <Metric label="Predicted clearance"
          value={`${Math.round(result.predicted_clearance_min)} min`} />
        <Metric label="Road-closure likelihood" value={`${prob}%`} />
        <Metric label="Diversion"
          value={result.diversion_required ? 'Required' : 'Not needed'} />
      </div>

      <div className="plan">
        <div className="plan-item">
          <span className="big">{result.manpower}</span>
          <span>officers / wardens</span>
        </div>
        <div className="plan-item">
          <span className="big">{result.barricades}</span>
          <span>barricade units</span>
        </div>
      </div>

      <div className="advice">
        <h4>Diversion advice</h4>
        <p>{result.diversion_advice}</p>
      </div>

      <div className="drivers">
        <h4>Why this plan?</h4>
        <ul>
          {result.drivers.map((d, i) => <li key={i}>{d}</li>)}
        </ul>
      </div>
    </div>
  )
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span className="metric-value">{value}</span>
      <span className="metric-label">{label}</span>
    </div>
  )
}
