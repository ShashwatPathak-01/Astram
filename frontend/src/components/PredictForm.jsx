import { useState } from 'react'
import { api } from '../api'

// Capitalise / prettify a raw category value for display.
const pretty = (s) => (s || '').replace(/_/g, ' ')

/**
 * PredictForm collects the event attributes and asks the backend for a
 * forecast + resource plan. Dropdown options come from the model metadata
 * (the actual category vocabulary the model was trained on).
 */
export default function PredictForm({ vocab, picked, onResult }) {
  const [form, setForm] = useState({
    event_type: 'unplanned',
    event_cause: 'accident',
    priority: 'High',
    veh_type: 'unknown',
    corridor: 'Hosur Road',
    zone: 'unknown',
    requires_road_closure: false,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const set = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm((f) => ({ ...f, [k]: v }))
  }

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const payload = {
        ...form,
        latitude: picked?.lat ?? 12.9716,
        longitude: picked?.lng ?? 77.5946,
        start_datetime: new Date().toISOString(),
      }
      const res = await api.predict(payload)
      onResult(res)
    } catch (err) {
      setError(String(err.message || err))
    } finally {
      setLoading(false)
    }
  }

  const opts = (key, fallback = []) =>
    (vocab?.[key] || fallback).map((v) => (
      <option key={v} value={v}>{pretty(v)}</option>
    ))

  return (
    <form className="card form" onSubmit={submit}>
      <h3>Forecast & plan an event</h3>

      <label>Event type
        <select value={form.event_type} onChange={set('event_type')}>
          {opts('event_type', ['planned', 'unplanned'])}
        </select>
      </label>

      <label>Cause
        <select value={form.event_cause} onChange={set('event_cause')}>
          {opts('event_cause')}
        </select>
      </label>

      <div className="row">
        <label>Priority
          <select value={form.priority} onChange={set('priority')}>
            {opts('priority', ['High', 'Low'])}
          </select>
        </label>
        <label>Vehicle
          <select value={form.veh_type} onChange={set('veh_type')}>
            <option value="unknown">unknown</option>
            {opts('veh_type')}
          </select>
        </label>
      </div>

      <label>Corridor
        <select value={form.corridor} onChange={set('corridor')}>
          {opts('corridor', ['Non-corridor'])}
        </select>
      </label>

      <label>Zone
        <select value={form.zone} onChange={set('zone')}>
          <option value="unknown">unknown</option>
          {opts('zone')}
        </select>
      </label>

      <label className="check">
        <input type="checkbox" checked={form.requires_road_closure}
          onChange={set('requires_road_closure')} />
        Road closure already known to be required
      </label>

      <p className="coords">
        Location: {picked ? `${picked.lat.toFixed(4)}, ${picked.lng.toFixed(4)}`
          : 'click the map to choose'}
      </p>

      <button type="submit" disabled={loading}>
        {loading ? 'Forecasting…' : 'Forecast impact & plan resources'}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  )
}
