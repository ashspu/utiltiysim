# Build from repository root. Template only: no image/deployment has been published.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY utilsim ./utilsim
COPY api ./api
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home runtime
USER runtime
ENV UTILITYSIM_DATA_ROOT=/data
EXPOSE 8080
CMD ["uvicorn", "utilsim.hosted.server:from_environment", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
