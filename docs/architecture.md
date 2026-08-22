# Architecture

```text
Browser
  │ HTTPS / same-origin session + CSRF
  ▼
FastAPI control plane
  ├── SQLite configuration and audit
  ├── encrypted secret vault
  ├── deterministic policy engine
  ├── provider adapters
  │    ├── Codex device-code auth + text-only subscription requests
  │    └── OpenAI-compatible Responses API
  └── allowlisted Asterisk renderer + atomic apply

Optional Asterisk gateway
  ├── PJSIP registration to existing PBX
  ├── RTP termination
  ├── ARI on loopback only
  └── Stasis application boundary
```

## Trust boundaries

1. **Browser:** receives configuration and status, never decrypted secrets.
2. **Control plane:** owns user sessions, policies, encrypted configuration and audit.
3. **Provider:** receives only the bounded conversation instructions/input needed for a response.
4. **Gateway:** owns SIP/RTP. It must not have access to provider credentials or the application database.
5. **PBX:** remains authoritative for trunks, dial permissions and emergency routing.

The `asterisk-config` volume crosses the control-plane/gateway boundary and contains a generated `pjsip.conf` with the SIP password. It is not a source artifact, must remain host-local, and must be protected like a secret. Provider credentials and the application database are never mounted into the gateway.

## Media-runtime boundary

This release supplies the SIP/RTP gateway, live configuration reload and ARI/Stasis boundary. A production ARI media worker (recording/streaming, STT, TTS, barge-in and bridge verification) is deliberately not represented as complete. It must be selected and validated against the target PBX and media providers before production use. The deterministic simulator exercises routing policy without claiming media-path validation.

## Deterministic call policy

The model may classify language and compose a short answer. It may not select arbitrary numbers, execute commands or bridge a call. The policy engine requires:

1. matching an enabled intent rule;
2. collecting configured required fields;
3. resolving a destination from the explicit allowlist;
4. consulting that destination;
5. explicit acceptance when enabled;
6. verified bridge completion.

Ambiguous consent fails closed. Missing routes become message-taking outcomes.

## Data model

- `users`: local administrators;
- `sessions`: hashed opaque session tokens and CSRF tokens;
- `settings`: versioned public configuration;
- `secrets`: Fernet ciphertext only;
- `audit_log`: actor/action metadata without secret payloads;
- `calls`: structured outcomes, with content retention intentionally separate.

## Codex authentication

The adapter uses Codex app-server protocol v2:

- `initialize` / `initialized`;
- `account/login/start` with `{ "type": "chatgptDeviceCode" }`;
- `account/login/cancel`;
- `account/read`;
- `account/login/completed` notification.

The stdio transport is JSONL and intentionally omits a `jsonrpc` field, matching the pinned Codex app-server contract. The implementation sends `account/read` with an explicit `refreshToken` boolean and drains stderr separately from protocol stdout.

Each installation has its own `CODEX_HOME`. The dashboard displays only the one-time code, verification URL and redacted account status.

Subscription inference remains experimental because it reaches the ChatGPT Codex response backend, which is not a stable general-purpose public API. It is isolated to text-only requests and never exposes Codex agent tools to calls. Deployments requiring a supported API contract must select the OpenAI-compatible provider instead.
