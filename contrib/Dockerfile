FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project --locked

COPY src/ src/
RUN uv sync --no-dev --locked

FROM python:3.13-slim

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

RUN groupadd --system titlani && useradd --system --gid titlani titlani

RUN mkdir -p /etc/titlani /var/lib/titlani/mailboxes \
    && chown -R titlani:titlani /var/lib/titlani

EXPOSE 1958
EXPOSE 1960

USER titlani

ENTRYPOINT ["titlani"]
CMD ["serve", "--config", "/etc/titlani/server.toml"]
