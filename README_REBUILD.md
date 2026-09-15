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

The frontend reads `VITE_API_URL` when running Vite directly; in production it uses the Node server's `/api` proxy. The API exposes `/api/health`, `/api/weeks`, and `/api/predictions`.

## Node.js deployment

The production web shell is now Node.js/Express. Build the React app and start the server with:

```bash
npm install
npm run build
PREDICTOR_API_URL=https://your-api-host.example.com npm start
```

`render.yaml` defines both services for deployment together: a Node web service and the FastAPI prediction service. Render wires `PREDICTOR_API_URL` to the API service automatically. The existing Streamlit app remains available during the migration.

## Install it on an iPhone

After the Node site is deployed over HTTPS, open its URL in Safari, tap **Share**, choose **Add to Home Screen**, leave **Open as Web App** enabled, and tap **Add**. It will open full-screen like an app and use `assets/cfb_icon.png` as its football icon. To change the artwork, replace that PNG, redeploy, then remove and reinstall the Home Screen icon so iOS picks up the new artwork.
