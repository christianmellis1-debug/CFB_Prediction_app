import express from 'express';
import cors from 'cors';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createProxyMiddleware} from 'http-proxy-middleware';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const port = Number(process.env.PORT || 3000);
const configuredApi = process.env.PREDICTOR_API_URL || 'http://localhost:8000';
const apiUrl = /^https?:\/\//i.test(configuredApi) ? configuredApi : `https://${configuredApi}`;

app.use(cors());
app.use('/api', createProxyMiddleware({target: apiUrl, changeOrigin: true, pathRewrite: {'^/api': '/api'}}));
app.use('/assets', express.static(path.join(__dirname, '..', 'assets')));
app.use(express.static(path.join(__dirname, '..', 'frontend', 'dist')));
app.use((_req, res) => res.sendFile(path.join(__dirname, '..', 'frontend', 'dist', 'index.html')));
app.listen(port, () => console.log(`CFB Predictor web server listening on ${port}; API: ${apiUrl}`));
