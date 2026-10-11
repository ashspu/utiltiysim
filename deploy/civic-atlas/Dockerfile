# Build from the repository root:
# docker build -f deploy/civic-atlas/Dockerfile -t utilitysim-atlas .
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY utilsim ./utilsim
COPY api ./api
RUN pip install --no-cache-dir .
COPY schemas ./schemas
COPY packs ./packs
COPY packages/town-viewer/dist ./packages/town-viewer/dist
COPY prototypes/civic-atlas ./prototypes/civic-atlas
RUN useradd --uid 10001 --create-home atlas && mkdir /data && chown atlas:atlas /data
USER atlas
VOLUME ["/data"]
EXPOSE 8044
CMD ["python", "prototypes/civic-atlas/server.py", "--library", "--host", "0.0.0.0", "--port", "8044", "--store", "/data"]
