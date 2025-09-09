FROM python:3.11.8-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /uvx /bin/
ENV UV_SYSTEM_PYTHON=1
COPY requirements.txt .
RUN uv pip install --require-hashes -r requirements.txt --no-deps
ENV APP_PORT=8080
EXPOSE 8080
WORKDIR /app
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$APP_PORT ads_placement_guardian.server:app"]
