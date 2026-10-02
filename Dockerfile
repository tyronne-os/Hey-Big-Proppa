# BIG PROPPA -- one container, backend + pre-built frontend, Docker SDK (no Gradio).
# Frontend is pre-built locally; dist/ is committed to the Space repo so Docker
# only needs to install Python deps and copy files — no Node or npm required.

FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY lake/gold/nfl/ lake/gold/nfl/
COPY frontend/dist/ frontend/dist/

WORKDIR /app/backend
EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
