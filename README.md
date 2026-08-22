# Voice Agent Studio

Voice Agent Studio is a self-hosted, browser-managed control plane for SIP voice agents. It keeps routing and consent deterministic while allowing interchangeable model, speech-to-text and text-to-speech providers.

> **Status:** v0.1.0. The dashboard, encrypted configuration store, deterministic policy simulator, Codex device-code authorization, API-provider adapter, Asterisk configuration and deployment manifests are implemented. Production call-media operation still requires validation against the target PBX and the selected STT/TTS providers. Never treat SIP registration alone as end-to-end acceptance.

## Why this project exists

- Users administer everything from a browser.
- The server—not the user's workstation—runs the required components.
- ChatGPT/Codex can be used as an inexpensive, experimental provider through the user's own subscription.
- OpenAI-compatible APIs remain the stable production option.
- The model cannot independently select arbitrary extensions or approve a transfer.
- Secrets, recordings and transcripts are excluded from source control by default.

## Quick start (Docker)

Requirements: Linux, Docker Engine and Docker Compose v2.

```bash
git clone <repository-url>
cd voice-agent-studio
./scripts/bootstrap.sh
docker compose up -d --build
```

Open `http://127.0.0.1:8080` through an SSH local forward, VPN, or authenticated reverse proxy. The first browser session creates the administrator.

The HTTP service binds to loopback by default. Do not expose it directly to the Internet.

## Native development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
export VAS_MASTER_KEY="$(python -m voice_agent_studio.cli generate-key)"
export VAS_DATA_DIR="$PWD/data"
uvicorn voice_agent_studio.main:app --host 127.0.0.1 --port 8080
```

Run checks:

```bash
ruff check .
pytest -q
```

## ChatGPT/Codex subscription mode

The production image bundles the official Codex component. The browser user does **not** install Codex.

1. Select **ChatGPT / Codex — economical (experimental)**.
2. Click **Connect account**.
3. The backend starts `account/login/start` with `chatgptDeviceCode` on an isolated Codex app-server.
4. The dashboard displays OpenAI's verification URL and one-time code.
5. The user signs in directly at OpenAI.
6. Codex stores the account tokens under the application's private data volume.
7. Model inference uses a text-only HTTPS adapter. It does not invoke Codex shell, filesystem, MCP or coding tools.

This path uses an official Codex login flow, but the ChatGPT Codex response endpoint is not a general public API contract. It can change. Use an API provider for workloads requiring a stable commercial interface.

## Telephony gateway

The optional gateway profile builds Asterisk/PJSIP:

```bash
# Add PBX values to the private .env file first.
docker compose --profile telephony up -d --build
```

Host networking is intentional for predictable SIP/RTP on Linux. Review firewall rules and the RTP range before enabling the profile. Never publish ARI; its template binds to loopback.

The dashboard renders a sanitized Asterisk preview. **Apply to gateway** writes three fixed, validated files to a private named volume and triggers an Asterisk reload; it never accepts arbitrary paths or configuration text. The generated `pjsip.conf` necessarily contains the SIP credential and is mode `0600`, but that credential is never returned by the API or committed to Git.

The shipped gateway terminates SIP/RTP and exposes the Stasis boundary. The repository does not yet include a production media worker for live STT/TTS turn handling; use the simulator to validate policies and integrate a reviewed ARI media worker before placing real calls.

## Security defaults

- PBKDF2-SHA256 administrator passwords (600,000 iterations).
- HttpOnly, SameSite=Strict sessions.
- CSRF token required for state-changing authenticated calls.
- Fernet-encrypted secrets with a mode-`0600` Docker secret as the external master key.
- Dashboard bound to loopback by default.
- Deny-by-default model tools and external calls.
- Explicit destination allowlist.
- Explicit destination acceptance and fail-closed consent.
- Recording and transcript retention disabled.
- Structured audit log without secret values.
- Container runs unprivileged, read-only and without Linux capabilities.

See [SECURITY.md](SECURITY.md) and [docs/architecture.md](docs/architecture.md).

## Project layout

```text
voice_agent_studio/   FastAPI API, dashboard and policy engine
deploy/asterisk/      Isolated SIP/RTP gateway image and templates
tests/                Synthetic unit and API tests
scripts/              Safe bootstrap utilities
docs/                 Architecture, deployment and threat model
```

## License

AGPL-3.0-only. See [LICENSE](LICENSE).
