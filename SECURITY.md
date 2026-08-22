# Security policy

## Reporting

Do not open a public issue containing credentials, PBX addresses, phone numbers, call recordings or transcripts. Use the repository's private security-advisory channel when available.

## Deployment rules

1. Keep the dashboard on loopback, a management VLAN, VPN or identity-aware proxy.
2. Set `VAS_SECURE_COOKIES=true` behind HTTPS.
3. Store `.env` as mode `0600`; prefer a secret manager for production.
   The bootstrap stores the encryption key separately at `secrets/master_key`, also mode `0600`.
4. Back up the database and master key separately. Losing the key makes encrypted provider and SIP secrets unrecoverable.
5. Never mount arbitrary host directories into the model or gateway containers.
6. Restrict PBX signaling by source address. Restrict RTP to the configured range.
7. Do not publish Asterisk ARI or AMI.
8. Obtain legal approval before enabling recording or transcript retention.
9. Treat the `asterisk-config` Docker volume as secret because applied PJSIP configuration contains the SIP password.

## Codex threat boundary

Codex app-server is used only for user-managed authentication. Phone-call inference is a direct text request and does not expose shell, filesystem, MCP servers or arbitrary tools. Credentials live in an isolated application data directory and never reach the browser.

The subscription adapter is experimental because its inference endpoint is not a stable general-purpose public API. Disable it if organizational policy requires only documented commercial APIs.

## Repository hygiene

The following must never be committed:

- `.env` and secret files;
- Codex `auth.json` or token caches;
- database files;
- SIP passwords;
- call recordings or packet captures;
- transcripts, caller IDs or client directories;
- production logs;
- private certificates and keys.
