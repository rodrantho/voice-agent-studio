import json

import pytest

from voice_agent_studio.providers import CodexSubscriptionProvider, ProviderError


def test_codex_reads_synthetic_credentials_without_exposing_them(tmp_path):
    token = "synthetic-token-not-a-real-secret"
    account = "synthetic-account"
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({"tokens": {"access_token": token, "account_id": account}}))
    auth_file.chmod(0o600)
    provider = CodexSubscriptionProvider(tmp_path)
    assert provider._credentials() == (token, account)


def test_codex_rejects_missing_credentials(tmp_path):
    provider = CodexSubscriptionProvider(tmp_path)
    with pytest.raises(ProviderError):
        provider._credentials()


def test_codex_rejects_world_readable_credentials(tmp_path):
    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"tokens":{"access_token":"x","account_id":"y"}}')
    auth_file.chmod(0o644)
    with pytest.raises(ProviderError, match="permissions"):
        CodexSubscriptionProvider(tmp_path)._credentials()
