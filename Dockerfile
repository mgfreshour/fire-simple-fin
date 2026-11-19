# Build stage: compile the frontend
FROM node:22-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Production stage: backend serves API + static frontend
FROM python:3.12-slim

WORKDIR /app/backend

RUN pip install --no-cache-dir uv

COPY backend/ ./
RUN uv sync --frozen --no-dev --no-cache

COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

ENV LISTEN_URL=0.0.0.0:8080
ENV DATABASE_PATH=/app/backend/data/firesimplefin.db
ENV FRONTEND_DIST=/app/frontend/dist

RUN mkdir -p /app/backend/data

EXPOSE 8080

CMD ["uv", "run", "--no-dev", "--frozen", "uvicorn", "firesimplefin.main:app", "--host", "0.0.0.0", "--port", "8080"]
