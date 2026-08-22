# Contributing to Voice Agent Studio

Thanks for helping improve the project.

## Before opening an issue

- Search existing issues.
- Include the PBX product and version when reporting SIP behavior.
- Remove passwords, API keys, phone numbers, transcripts, and customer data.
- Reproduce with a dedicated test extension, never with Ariel or a production account.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/pytest -q
```

## Pull requests

Keep changes focused. Explain the operational impact, security implications, and how you tested the change. Do not add provider credentials, PBX exports, recordings, or customer data to the repository.
