import { useEffect, useState } from 'react'
import { api } from './api'
import MapView from './components/MapView'
import PredictForm from './components/PredictForm'
import ResultCard from './components/ResultCard'
import Analytics from './components/Analytics'

export default function App() {
  const [tab, setTab] = useState('planner')
  const [vocab, setVocab] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [events, setEvents] = useState([])
  const [analytics, setAnalytics] = useState(null)
  const [picked, setPicked] = useState({ lat: 12.9716, lng: 77.5946 })
  const [result, setResult] = useState(null)
  const [apiUp, setApiUp] = useState(null)

  // Load everything the dashboard needs up-front.
  useEffect(() => {
    api.health().then((h) => setApiUp(h.models_loaded)).catch(() => setApiUp(false))
    api.metadata().then((m) => {
      setVocab(m.category_vocab)
      setMetrics({ regression: m.regression, classification: m.classification })
    }).catch(() => {})
    api.events(1200).then((d) => setEvents(d.events)).catch(() => {})
    api.analytics().then(setAnalytics).catch(() => {})
  }, [])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">▦</span>
          <div>
            <h1>Astram Congestion Planner</h1>
            <p>Forecast event-driven traffic impact &amp; recommend deployment</p>
          </div>
        </div>
        <nav>
          <button className={tab === 'planner' ? 'active' : ''}
            onClick={() => setTab('planner')}>Planner</button>
          <button className={tab === 'analytics' ? 'active' : ''}
            onClick={() => setTab('analytics')}>Analytics</button>
        </nav>
        <div className="model-badge">
          {metrics ? (
            <>
              <span>Impact model: <b>{metrics.regression.best_model}</b></span>
              <span>Closure model: <b>{metrics.classification.best_model}</b>
                {' '}(AUC {metrics.classification.candidates[metrics.classification.best_model].roc_auc})</span>
            </>
          ) : (
            <span className={apiUp === false ? 'down' : ''}>
              {apiUp === false ? 'API offline — start the backend' : 'Connecting…'}
            </span>
          )}
        </div>
      </header>

      {tab === 'planner' ? (
        <main className="planner">
          <section className="left">
            <PredictForm vocab={vocab} picked={picked} onResult={setResult} />
            <ResultCard result={result} />
          </section>
          <section className="right">
            <MapView events={events} picked={picked} onPick={setPicked} />
            <Legend />
          </section>
        </main>
      ) : (
        <main className="analytics-page">
          <Analytics analytics={analytics} />
        </main>
      )}

      <footer className="footer">
        Built on the Astram Bengaluru event log · Models trained in
        {' '}<code>notebook/traffic_event_model.ipynb</code> · Map by Mappls (MapmyIndia)
      </footer>
    </div>
  )
}

function Legend() {
  const items = [
    ['#ef4444', 'Accident'],
    ['#f59e0b', 'Obstruction (construction, tree fall, water-logging…)'],
    ['#8b5cf6', 'Crowd / congestion (events, processions…)'],
    ['#2563eb', 'Breakdown / other'],
  ]
  return (
    <div className="legend">
      {items.map(([c, l]) => (
        <span key={l}><i style={{ background: c }} />{l}</span>
      ))}
    </div>
  )
}
