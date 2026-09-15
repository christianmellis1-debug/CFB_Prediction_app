# CFB Predictor rebuild

The new app lives alongside the existing Streamlit app so the migration can be tested safely.

## Run locally

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
cd frontend
npm install
npm run dev
```

The frontend reads `VITE_API_URL` (default `http://localhost:8000`). The API exposes `/api/health`, `/api/weeks`, and `/api/predictions`.

## Node.js deployment

The production web shell is now Node.js/Express. Build the React app and start the server with:

```bash
npm install
npm run build
PREDICTOR_API_URL=https://your-api-host.example.com npm start
```

`render.yaml` is included for a one-click Node web-service setup. Set `PREDICTOR_API_URL` to the deployed prediction API URL. The existing FastAPI service remains available during the migration so the model and live data stay unchanged while the web runtime moves to Node.
