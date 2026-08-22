import sys

import pytest

from voice_agent_studio.providers import CodexAppServer


@pytest.mark.asyncio
async def test_codex_app_server_device_login_contract(tmp_path):
    fake = tmp_path / "fake_codex.py"
    fake.write_text(
        """import json, sys
for line in sys.stdin:
    message = json.loads(line)
    assert 'jsonrpc' not in message
    if 'id' not in message:
        continue
    method = message['method']
    if method == 'initialize':
        result = {'serverInfo': {'name': 'fake', 'version': '1'}}
    elif method == 'account/login/start':
        assert message['params'] == {'type': 'chatgptDeviceCode'}
        result = {
            'type': 'chatgptDeviceCode',
            'loginId': 'login-1',
            'userCode': 'ABCD-EFGH',
            'verificationUrl': 'https://example.invalid/device',
        }
    elif method == 'account/read':
        assert message['params'] == {'refreshToken': False}
        result = {'account': {'type': 'chatgpt', 'email': None, 'planType': 'plus'}}
    elif method == 'account/login/cancel':
        result = {'status': 'cancelled'}
    elif method == 'account/logout':
        result = {'status': 'loggedOut'}
    else:
        result = {}
    print(json.dumps({'id': message['id'], 'result': result}), flush=True)
"""
    )
    server = CodexAppServer(f"{sys.executable} {fake}", tmp_path / "codex-home")
    try:
        login = await server.begin_device_login()
        assert login.login_id == "login-1"
        assert login.user_code == "ABCD-EFGH"
        assert login.verification_url == "https://example.invalid/device"
        account = await server.account()
        assert account["account"]["planType"] == "plus"
        assert (await server.cancel_login("login-1"))["status"] == "cancelled"
        assert (await server.logout())["status"] == "loggedOut"
    finally:
        await server.close()
