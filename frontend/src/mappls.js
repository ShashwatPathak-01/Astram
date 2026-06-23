// Loads the Mappls (MapMyIndia) Web Map SDK exactly once.
//
// Security: the client_id / client_secret never touch the browser. Instead the
// FastAPI backend exchanges them for a short-lived OAuth access token via
// /api/maps/token, and we inject the SDK <script> using that token.

import { api } from './api'

let sdkPromise = null

export function loadMapplsSdk() {
  if (sdkPromise) return sdkPromise

  sdkPromise = (async () => {
    // Already present (hot reload) ?
    if (window.mappls && window.mappls.Map) return window.mappls

    const { access_token } = await api.mapToken()
    if (!access_token) throw new Error('No Mappls access token returned')

    await new Promise((resolve, reject) => {
      const cbName = 'initMapplsSdk_' + Date.now()
      window[cbName] = () => resolve()

      const script = document.createElement('script')
      script.src =
        `https://apis.mappls.com/advancedmaps/api/${access_token}` +
        `/map_sdk?layer=vector&v=3.0&callback=${cbName}`
      script.async = true
      script.defer = true
      script.onerror = () => reject(new Error('Failed to load Mappls SDK script'))
      document.head.appendChild(script)
    })

    if (!window.mappls || !window.mappls.Map) {
      throw new Error('Mappls SDK loaded but window.mappls.Map is missing')
    }
    return window.mappls
  })()

  return sdkPromise
}
