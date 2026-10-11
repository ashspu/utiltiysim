# Build from repository root. Base digest and uv version verified 2026-10-11.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.revision=$SOURCE_REVISION
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY utilsim ./utilsim
COPY api ./api
RUN pip install --no-cache-dir uv==0.13.0 \
    && uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python \
    && useradd --uid 10001 --create-home runtime \
    && mkdir /data && chown runtime:runtime /data
ENV PATH="/app/.venv/bin:$PATH"
USER runtime
ENV UTILITYSIM_DATA_ROOT=/data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=6s --start-period=20s --retries=3 CMD ["python", "-m", "utilsim.hosted.health"]
CMD ["uvicorn", "utilsim.hosted.server:from_environment", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
