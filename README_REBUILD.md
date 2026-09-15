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
