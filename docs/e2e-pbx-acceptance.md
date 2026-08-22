# PBX E2E acceptance test

This procedure validates the complete product path against a real PBX and a dedicated SIP extension.

## Required inputs

- PBX hostname or IP.
- SIP transport: UDP or TCP.
- Dedicated extension and authentication password.
- One allowed transfer destination.
- STT and TTS credentials, or configured local providers.
- A test caller that can reach the agent extension.

Do not use Ariel's extension, credentials, routing, or production instance for this test.

## Test sequence

1. Start the application locally:

   ```bash
   ./scripts/bootstrap.sh
   docker compose up -d --build
   ```

2. Open `http://127.0.0.1:8080` and create the administrator.
3. Configure the dedicated SIP extension under **Telefonía**.
4. Save the SIP secret and select **Guardar y conectar**.
5. Confirm the dashboard reports:
   - SIP process active;
   - registration confirmed;
   - no authentication or transport error.
6. Place an inbound test call to the agent extension.
7. Confirm the agent answers and produces bidirectional audio.
8. Say a known test phrase and confirm STT appears in the resulting behavior.
9. Confirm the response is rendered through TTS.
10. Request a transfer to the allowed destination.
11. Confirm the agent asks for caller consent.
12. Confirm the destination receives the consultation call and accepts it with DTMF `1`.
13. Confirm the attended bridge completes and both legs remain audible.
14. Hang up and verify the call is recorded in the dashboard without raw secrets.

## Evidence to record

- PBX type and version.
- SIP transport and codec negotiated.
- Registration time.
- Call setup time.
- STT/TTS providers and model names, never API keys.
- Transfer result.
- Any SIP or RTP error.
- A short redacted screen recording or screenshots.

## Acceptance criteria

The release passes only if all of these are true:

- `REGISTER` succeeds and remains registered for 10 minutes.
- Incoming audio and outgoing audio both work.
- STT receives the caller's phrase correctly enough for routing.
- TTS is audible to the caller.
- Ambiguous consent does not transfer.
- Explicit consent transfers only to an allowlisted destination.
- A failed destination call returns the caller to a deterministic fallback.
- No password, API key, or transcript appears in logs, exports, or screenshots.

A SIP registration check alone is **not** an E2E acceptance test.
