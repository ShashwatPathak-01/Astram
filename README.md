# Astram — Event-Driven Congestion Planner

Forecast the traffic impact of planned & unplanned events (rallies, festivals,
construction, accidents, breakdowns…) and recommend an **optimal manpower,
barricading and diversion plan** — built on the Astram Bengaluru event log
(~8,200 real events, Nov 2023 – Apr 2024).

> **Hackathon problem:** *How can historical and real-time data be used to
> forecast event-related traffic impact and recommend optimal manpower,
> barricading and diversion plans?*

---

## What's inside

| Layer | Tech | Folder |
|-------|------|--------|
| **ML / modelling** | Python, scikit-learn, Jupyter | [`notebook/`](notebook/), [`backend/ml/`](backend/ml/) |
| **Backend API** | FastAPI | [`backend/`](backend/) |
| **Frontend** | React + JavaScript (Vite) | [`frontend/`](frontend/) |
| **Map** | Mappls (MapmyIndia) Web SDK | [`frontend/src/mappls.js`](frontend/src/mappls.js) |

### The models

1. **Clearance-duration regression** — predicts how long an event blocks the
   road (the *impact* proxy). Gradient-boosted; median error ≈ 25 min.
2. **Road-closure classifier** — predicts whether barricading / diversion is
   needed (ROC-AUC ≈ 0.80). Leakage from the "end point" field was found and
   removed (see the notebook, §3.1).
3. **Resource recommender** — a transparent rule engine on top of the two
   predictions that outputs a 0–100 severity score, manpower, barricade count
   and a written diversion plan.

The notebook and the backend share the **exact same** feature-engineering and
training code in [`backend/ml/`](backend/ml/), so what you see trained in the
notebook is what the API serves.

---

## Quick start

### 1. Backend (Python / FastAPI)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# (Optional) train the models — pre-trained artifacts are already in models/
python -m ml.train --csv "../Astram event data_anonymized - Astram event data_anonymizedb40ac87.csv" --out models

# Add your Mappls credentials so the map works
cp .env.example .env        # then edit MAPPLS_CLIENT_ID / MAPPLS_CLIENT_SECRET

uvicorn app.main:app --reload --port 8000
```

API docs are auto-generated at <http://127.0.0.1:8000/docs>.

### 2. Frontend (React / Vite)

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api -> :8000)
```

### 3. Notebook

```bash
cd notebook
jupyter lab traffic_event_model.ipynb
```

---

## Mappls (MapmyIndia) setup

1. Create an account at <https://apis.mappls.com/console/> and generate a
   **REST API** key pair (client id + client secret).
2. Put them in `backend/.env`:
   ```
   MAPPLS_CLIENT_ID=xxxxxxxx
   MAPPLS_CLIENT_SECRET=yyyyyyyy
   ```
3. The **secret never reaches the browser**: the backend exchanges it for a
   short-lived OAuth access token via `GET /api/maps/token`, and the React app
   loads the Map SDK with that token. Without credentials the UI degrades
   gracefully to a coordinate picker so the planner still works.

---

## API reference

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/health` | Service + model status |
| `GET`  | `/api/metadata` | Category vocab (dropdowns) + model metrics |
| `GET`  | `/api/analytics` | Pre-computed hotspot aggregates |
| `GET`  | `/api/events?limit=` | Sample of geolocated events for the map |
| `POST` | `/api/predict` | Forecast + full resource plan for one event |
| `POST` | `/api/predict/batch` | Same, for a list of events |
| `GET`  | `/api/maps/token` | Server-side Mappls OAuth token |

**Example**

```bash
curl -X POST http://127.0.0.1:8000/api/predict \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"planned","event_cause":"public_event","priority":"High",
       "corridor":"Mysore Road","latitude":12.95,"longitude":77.58,
       "requires_road_closure":true}'
```

```json
{
  "severity": "High", "severity_score": 63.6,
  "predicted_clearance_min": 80.5, "road_closure_probability": 0.666,
  "manpower": 14, "barricades": 10, "diversion_required": true,
  "diversion_advice": "Set up a signed diversion off 'Mysore Road'. …",
  "drivers": ["Base 8 for High severity", "+2 on arterial corridor 'Mysore Road'", …]
}
```

---

## How it addresses the operational challenge

| Pain point today | What this delivers |
|------------------|--------------------|
| Impact not quantified in advance | Clearance-time forecast + 0–100 severity score per event |
| Resource deployment is experience-driven | Data-driven manpower / barricade / diversion plan **with rationale** |
| No post-event learning | Models retrain from the same growing event log |
