# Voice Agent Studio

[Español](README.md) | **English** | [Deutsch](README.de.md)

A self-hosted web application for deploying a telephone agent on the same network as an existing PBX and registering it as a standard SIP extension.

## How it works

```text
Existing PBX ← SIP/RTP → Voice Agent Studio
                              ├─ Headless Linphone
                              ├─ STT
                              ├─ Language model
                              ├─ TTS
                              └─ Consult and attended transfer
```

The application **does not install or manage the PBX**. The operator only creates or provides a dedicated SIP extension and configures its credentials through the browser.

## Capabilities

- Direct SIP registration over UDP or TCP.
- Automatic answering of incoming calls.
- Turn-based conversation with voice and silence detection.
- STT through OpenAI, Deepgram, or a server-managed local command.
- TTS through OpenAI, ElevenLabs, or local Piper.
- OpenAI-compatible models and experimental ChatGPT/Codex connectivity.
- Deterministic directory and routing rules.
- Extension consultation, explicit acceptance, and attended transfer.
- Encrypted secrets, administrative sessions, CSRF protection, and auditing.
- Process and SIP registration diagnostics from the dashboard.

## Installation

Requirements: Linux, Docker Engine, and Docker Compose.

```bash
git clone https://github.com/rodrantho/voice-agent-studio.git
cd voice-agent-studio
./scripts/bootstrap.sh
docker compose up -d --build
```

Open `http://127.0.0.1:8080`. For access from another machine, publish it through an HTTPS reverse proxy or explicitly configure `VAS_BIND_HOST` in `.env`.

## Initial configuration

1. Create the administrator account.
2. Configure the agent identity and knowledge.
3. Enter the SIP server, port, transport, extension, username, and password.
4. Select **Save and connect** and verify the `Registered` status.
5. Configure the language model, STT, and TTS providers.
6. Add transfer destinations and routing rules.
7. Run the provider and voice tests.
8. Call the agent extension.

The PBX controls trunks, permissions, numbering, and routing. Authentication failures, timeouts, and rejections are displayed as SIP status information; the application does not attempt to modify the PBX.

## Security

- The dashboard binds to loopback by default.
- The master key remains outside the image and repository.
- Secrets are encrypted in SQLite.
- The runtime is unprivileged after startup.
- Calls have no access to the Docker socket, shell, or tools.
- Transfer destinations use an allowlist.
- Ambiguous consent fails closed.
- External calls are disabled by default.
- Recording and retention are disabled by default.

## Operational scope

Automated tests validate configuration, policies, SIP control, and security. Installation acceptance requires a real call using the dedicated extension: `REGISTER`, incoming call, bidirectional audio, STT, TTS, and transfer. Successful SIP registration alone does not prove that audio works.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/pytest -q
```

License: AGPL-3.0-only.
