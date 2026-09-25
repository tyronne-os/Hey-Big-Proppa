# BIG PROPPA -- one container, backend + frontend, Docker SDK (no Gradio anywhere).
# HF Spaces builds this from the repo root and expects the app on port 7860.

FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin: the built app calls /api/... on whatever host serves it, no CORS needed.
ENV VITE_API_BASE=""
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY lake/gold/nfl/ lake/gold/nfl/
COPY --from=frontend /app/frontend/dist/ frontend/dist/

WORKDIR /app/backend
EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
