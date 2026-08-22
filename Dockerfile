FROM node:22-bookworm-slim AS codex
ARG CODEX_VERSION=0.149.0
RUN npm install -g "@openai/codex@${CODEX_VERSION}"

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 --create-home vas
WORKDIR /app
COPY --from=codex /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
COPY --from=codex /usr/local/bin/codex /usr/local/bin/codex
COPY pyproject.toml README.md LICENSE ./
COPY voice_agent_studio ./voice_agent_studio
RUN pip install --no-cache-dir . \
    && mkdir -p /data /asterisk-config \
    && chown -R vas:vas /data /asterisk-config /home/vas
USER vas
ENV VAS_DATA_DIR=/data VAS_BIND_HOST=0.0.0.0 VAS_BIND_PORT=8080 VAS_CODEX_COMMAND="codex app-server"
EXPOSE 8080
CMD ["sh","-c","uvicorn voice_agent_studio.main:app --host $VAS_BIND_HOST --port $VAS_BIND_PORT --proxy-headers --forwarded-allow-ips=127.0.0.1"]
