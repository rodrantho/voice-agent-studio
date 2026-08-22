# Security Policy

## Supported version

Only the latest `main` revision is supported before the first stable release.

## Security defaults

- The web service binds to loopback by default.
- Administrative passwords use PBKDF2-SHA256.
- Sessions are HTTP-only, SameSite strict and CSRF-protected.
- SIP and provider secrets are encrypted at rest with an external Fernet key.
- The master key is never stored in the image or Git repository.
- The startup process copies the file-backed secret to tmpfs and drops all privileges before launching the application.
- The model has no tools, shell or filesystem access.
- Transfer destinations are allowlisted and destination acceptance is required by default.
- External calls, recording and transcript retention are disabled by default.
- The container has no Docker socket and uses a read-only root filesystem.

## Operator responsibilities

1. Use a SIP extension dedicated to this installation.
2. Put the dashboard behind HTTPS before exposing it beyond loopback.
3. Restrict SIP/RTP at the host firewall to the PBX and required media paths.
4. Keep Docker, Linphone and application images patched.
5. Protect and back up the master key separately from application data.
6. Obtain legal approval before recording calls or retaining transcripts.
7. Restrict the PBX extension's outbound permissions to the minimum required.
8. Review audit and call outcomes without storing secrets in tickets or documentation.

## Experimental provider

ChatGPT/Codex authorization uses a bundled, pinned Codex app-server and isolated `CODEX_HOME`. Subscription-backed inference remains experimental and is not a stable third-party API contract. Use a supported API provider where contractual stability is required.

## Reporting

Do not open public issues containing credentials, call audio, transcripts or customer data. Report security issues privately to the repository owner.
