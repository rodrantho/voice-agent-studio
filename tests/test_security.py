from voice_agent_studio.security import Vault, generate_master_key, hash_password, verify_password


def test_password_hash_roundtrip():
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)
    assert "correct horse" not in encoded


def test_vault_roundtrip():
    vault = Vault(generate_master_key().encode())
    encrypted = vault.encrypt("secret-value")
    assert b"secret-value" not in encrypted
    assert vault.decrypt(encrypted) == "secret-value"


def test_vault_loads_key_file(tmp_path, monkeypatch):
    key_file = tmp_path / "master_key"
    key_file.write_text(generate_master_key())
    monkeypatch.delenv("VAS_MASTER_KEY", raising=False)
    monkeypatch.setenv("VAS_MASTER_KEY_FILE", str(key_file))
    assert Vault.from_environment().decrypt(Vault.from_environment().encrypt("ok")) == "ok"
