// Thin API client for the FastAPI backend. All paths are relative so the Vite
// dev proxy (or same-origin deploy) routes them to the Python service.

const API_BASE =
  import.meta.env.VITE_API_URL || '';

async function jget(path) {
  const r = await fetch(`${API_BASE}${path}`)
  if (!r.ok) throw new Error(`${path} -> ${r.status}`)
  return r.json()
}

async function jpost(path, body) {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const text = await r.text()
    throw new Error(`${path} -> ${r.status}: ${text}`)
  }
  return r.json()
}

export const api = {
  health: () => jget('/api/health'),
  metadata: () => jget('/api/metadata'),
  analytics: () => jget('/api/analytics'),
  events: (limit = 1200) => jget(`/api/events?limit=${limit}`),
  predict: (event) => jpost('/api/predict', event),
  mapToken: () => jget('/api/maps/token'),
}
