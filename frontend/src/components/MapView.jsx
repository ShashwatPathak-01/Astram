import { useEffect, useRef, useState } from 'react'
import { loadMapplsSdk } from '../mappls'

const BENGALURU = [12.9716, 77.5946]

// Colour markers by event cause group so hotspots are visually obvious.
function colorFor(ev) {
  const c = (ev.event_cause || '').toLowerCase()
  if (['accident'].includes(c)) return '#ef4444'
  if (['construction', 'tree_fall', 'water_logging', 'pot_holes', 'road_conditions'].includes(c)) return '#f59e0b'
  if (['public_event', 'procession', 'vip_movement', 'protest', 'congestion'].includes(c)) return '#8b5cf6'
  return '#2563eb'
}

/**
 * MapView renders the live Bengaluru map (Mappls), plots historical events as
 * coloured markers, and lets the operator click the map to choose a location
 * for the forecast (bubbled up via onPick).
 */
export default function MapView({ events, picked, onPick }) {
  const mapDivRef = useRef(null)
  const mapRef = useRef(null)
  const pickMarkerRef = useRef(null)
  const [status, setStatus] = useState('loading') // loading | ready | error
  const [error, setError] = useState('')

  // Initialise the map once.
  useEffect(() => {
    let cancelled = false
    loadMapplsSdk()
      .then((mappls) => {
        if (cancelled) return
        const map = new mappls.Map(mapDivRef.current, {
          center: BENGALURU,
          zoom: 11,
        })
        mapRef.current = map
        const ready = () => {
          if (cancelled) return
          setStatus('ready')
          // Let the user pick a location by clicking the map.
          try {
            map.addListener('click', (e) => {
              const ll = e.lngLat || e.latlng || {}
              const lat = ll.lat ?? (Array.isArray(ll) ? ll[1] : undefined)
              const lng = ll.lng ?? (Array.isArray(ll) ? ll[0] : undefined)
              if (lat != null && lng != null) onPick({ lat, lng })
            })
          } catch (_) { /* listener API differences are non-fatal */ }
        }
        try { map.addListener('load', ready) } catch (_) { ready() }
        // Safety net in case the load event never fires.
        setTimeout(ready, 1500)
      })
      .catch((err) => {
        if (cancelled) return
        setError(String(err.message || err))
        setStatus('error')
      })
    return () => { cancelled = true }
  }, [])

  // Draw / refresh historical-event markers whenever data or readiness changes.
  useEffect(() => {
    if (status !== 'ready' || !mapRef.current || !window.mappls) return
    const mappls = window.mappls
    const map = mapRef.current
    const markers = []
    events.slice(0, 400).forEach((ev) => {
      try {
        const m = new mappls.Marker({
          map,
          position: { lat: ev.latitude, lng: ev.longitude },
          icon_url: undefined,
          html: `<div style="width:10px;height:10px;border-radius:50%;
                 background:${colorFor(ev)};border:1px solid #fff;
                 box-shadow:0 0 2px rgba(0,0,0,.4)"></div>`,
          popupHtml: `<b>${ev.event_cause || 'event'}</b><br/>${ev.corridor || ''}
                      <br/>${(ev.address || '').slice(0, 80)}`,
        })
        markers.push(m)
      } catch (_) { /* ignore individual marker failures */ }
    })
    return () => {
      markers.forEach((m) => { try { m.remove() } catch (_) {} })
    }
  }, [events, status])

  // Move the "picked location" marker when the selection changes.
  useEffect(() => {
    if (status !== 'ready' || !mapRef.current || !window.mappls || !picked) return
    const mappls = window.mappls
    try {
      if (pickMarkerRef.current) pickMarkerRef.current.remove()
      pickMarkerRef.current = new mappls.Marker({
        map: mapRef.current,
        position: { lat: picked.lat, lng: picked.lng },
        draggable: true,
        popupHtml: 'Selected event location',
      })
      try {
        pickMarkerRef.current.addListener('dragend', (e) => {
          const ll = e.lngLat || e.latlng || {}
          if (ll.lat != null) onPick({ lat: ll.lat, lng: ll.lng })
        })
      } catch (_) {}
    } catch (_) {}
  }, [picked, status])

  return (
    <div className="map-wrap">
      <div ref={mapDivRef} className="map" />
      {status !== 'ready' && (
        <div className="map-overlay">
          {status === 'loading' && <p>Loading Mappls map…</p>}
          {status === 'error' && (
            <div className="map-error">
              <h4>Map unavailable</h4>
              <p>{error}</p>
              <p className="hint">
                Add your Mappls <code>MAPPLS_CLIENT_ID</code> and{' '}
                <code>MAPPLS_CLIENT_SECRET</code> to <code>backend/.env</code> and
                restart the API. You can still use the planner and the location
                picker below.
              </p>
              <FallbackPicker picked={picked} onPick={onPick} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// When the map can't load (no credentials), still allow choosing coordinates.
function FallbackPicker({ picked, onPick }) {
  return (
    <div className="fallback-picker">
      <label>Lat
        <input type="number" step="0.0001" value={picked?.lat ?? 12.9716}
          onChange={(e) => onPick({ lat: parseFloat(e.target.value), lng: picked?.lng ?? 77.5946 })} />
      </label>
      <label>Lng
        <input type="number" step="0.0001" value={picked?.lng ?? 77.5946}
          onChange={(e) => onPick({ lat: picked?.lat ?? 12.9716, lng: parseFloat(e.target.value) })} />
      </label>
    </div>
  )
}
