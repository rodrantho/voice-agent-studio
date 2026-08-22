import importlib

from fastapi.testclient import TestClient

from voice_agent_studio.security import generate_master_key


def test_setup_login_config_and_csrf(tmp_path, monkeypatch):
    monkeypatch.setenv("VAS_MASTER_KEY", generate_master_key())
    monkeypatch.setenv("VAS_DATA_DIR", str(tmp_path))

    import voice_agent_studio.main as module
    module = importlib.reload(module)
    with TestClient(module.app) as client:
        assert client.get("/api/health").json()["setup_required"] is True
        headers = client.get("/api/health").headers
        assert headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in headers["content-security-policy"]
        setup = client.post("/api/setup", json={"username": "admin", "password": "very-strong-test-password"})
        assert setup.status_code == 200
        csrf = setup.json()["csrf_token"]
        config = client.get("/api/config")
        assert config.status_code == 200
        payload = config.json()["config"]
        assert payload["safety"]["allow_model_tools"] is False
        payload["sip"]["host"] = "pbx.example"
        payload["sip"]["extension"] = "200"
        assert client.put("/api/config", json=payload).status_code == 403
        saved = client.put("/api/config", headers={"X-CSRF-Token": csrf}, json=payload)
        assert saved.status_code == 200
        secret = client.put("/api/secrets", headers={"X-CSRF-Token": csrf}, json={"name": "sip_password", "value": "synthetic-password"})
        assert secret.status_code == 200
        reread = client.get("/api/config").json()
        assert reread["secrets"]["sip_password"] is True
        assert "synthetic-password" not in str(reread)
        async def fake_reload():
            return {"running": True, "registered": True, "detail": "registered"}
        module.sip_runtime.reload = fake_reload
        applied = client.post("/api/sip/apply", headers={"X-CSRF-Token": csrf})
        assert applied.status_code == 200
        assert "synthetic-password" not in applied.text
        assert applied.json()["status"]["registered"] is True

        class FakeCodex:
            async def account(self):
                return {
                    "account": {
                        "type": "chatgpt",
                        "planType": "plus",
                        "email": "private@example.invalid",
                    }
                }

        original_codex = module.codex
        module.codex = FakeCodex()
        status = client.get("/api/providers/codex/status")
        module.codex = original_codex
        assert status.json()["account"] == {"type": "chatgpt", "planType": "plus"}
        assert "private@example.invalid" not in status.text
