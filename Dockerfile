FROM node:22-bookworm-slim AS codex
ARG CODEX_VERSION=0.149.0
RUN npm install -g "@openai/codex@${CODEX_VERSION}"

FROM python:3.13-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       ca-certificates ffmpeg linphone-cli \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 vas \
    && useradd --system --uid 10001 --gid 10001 --create-home vas
WORKDIR /app
COPY --from=codex /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
COPY --from=codex /usr/local/bin/codex /usr/local/bin/codex
COPY pyproject.toml README.md LICENSE ./
COPY voice_agent_studio ./voice_agent_studio
COPY scripts/container-entrypoint.sh /usr/local/bin/vas-entrypoint
RUN pip install --no-cache-dir . \
    && chmod 0755 /usr/local/bin/vas-entrypoint \
    && install -d -o vas -g vas -m 0700 /data \
    && chown -R root:vas /app \
    && chmod -R g+rX /app
ENV VAS_DATA_DIR=/data \
    VAS_BIND_HOST=127.0.0.1 \
    VAS_BIND_PORT=8080 \
    VAS_CODEX_COMMAND="codex app-server"
EXPOSE 8080/udp 5062/udp 10000-10100/udp
ENTRYPOINT ["/usr/local/bin/vas-entrypoint"]
CMD ["sh","-c","exec uvicorn voice_agent_studio.main:app --host $VAS_BIND_HOST --port $VAS_BIND_PORT --proxy-headers --forwarded-allow-ips=127.0.0.1"]
