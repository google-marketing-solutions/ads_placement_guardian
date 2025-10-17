FROM python:3.11.8-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/
ADD uv.lock .
ADD README.md .
ADD googleads_housekeeper googleads_housekeeper/
ADD pyproject.toml .
RUN uv sync
