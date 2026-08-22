from __future__ import annotations

import asyncio
import json
import os
import shlex
import stat
from dataclasses import dataclass
from pathlib import Path

import httpx


class ProviderError(RuntimeError):
    pass


@dataclass
class CodexLogin:
    login_id: str
    verification_url: str
    user_code: str


class CodexAppServer:
    """JSON-RPC client for a deployment-bundled Codex app-server.

    Codex runs with an isolated CODEX_HOME. The browser user never installs it.
    No shell, MCP, filesystem or arbitrary tools are exposed by this adapter.
    """

    def __init__(self, command: str, codex_home: Path):
        self.command = shlex.split(command)
        self.codex_home = codex_home
        self.process: asyncio.subprocess.Process | None = None
        self.pending: dict[int, asyncio.Future] = {}
        self.notifications: asyncio.Queue[dict] = asyncio.Queue()
        self._reader: asyncio.Task | None = None
        self._stderr_reader: asyncio.Task | None = None
        self._sequence = 0
        self._start_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._start_lock:
            await self._start_unlocked()

    async def _start_unlocked(self) -> None:
        if self.process and self.process.returncode is None:
            return
        self.codex_home.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.codex_home, 0o700)
        env = {**os.environ, "CODEX_HOME": str(self.codex_home)}
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader = asyncio.create_task(self._read_loop())
        self._stderr_reader = asyncio.create_task(self._drain_stderr())
        await self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "voice_agent_studio",
                    "title": "Voice Agent Studio",
                    "version": "0.1.0",
                }
            },
        )
        await self.notify("initialized", {})

    async def _drain_stderr(self) -> None:
        assert self.process and self.process.stderr
        while await self.process.stderr.readline():
            pass

    async def _read_loop(self) -> None:
        assert self.process and self.process.stdout
        while line := await self.process.stdout.readline():
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in message and message["id"] in self.pending:
                future = self.pending.pop(message["id"])
                if "error" in message:
                    future.set_exception(ProviderError(str(message["error"])))
                else:
                    future.set_result(message.get("result"))
            else:
                await self.notifications.put(message)

    async def request(self, method: str, params: dict, timeout: float = 30) -> dict:
        await self.start_if_needed(method)
        assert self.process and self.process.stdin
        async with self._write_lock:
            self._sequence += 1
            request_id = self._sequence
            future = asyncio.get_running_loop().create_future()
            self.pending[request_id] = future
            payload = {"id": request_id, "method": method, "params": params}
            self.process.stdin.write((json.dumps(payload) + "\n").encode())
            await self.process.stdin.drain()
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(request_id, None)

    async def start_if_needed(self, method: str) -> None:
        if method != "initialize" and (not self.process or self.process.returncode is not None):
            await self.start()

    async def notify(self, method: str, params: dict) -> None:
        assert self.process and self.process.stdin
        async with self._write_lock:
            self.process.stdin.write(
                (json.dumps({"method": method, "params": params}) + "\n").encode()
            )
            await self.process.stdin.drain()

    async def begin_device_login(self) -> CodexLogin:
        result = await self.request("account/login/start", {"type": "chatgptDeviceCode"})
        return CodexLogin(
            login_id=result["loginId"],
            verification_url=result["verificationUrl"],
            user_code=result["userCode"],
        )

    async def cancel_login(self, login_id: str) -> dict:
        return await self.request("account/login/cancel", {"loginId": login_id})

    async def account(self, refresh_token: bool = False) -> dict:
        return await self.request("account/read", {"refreshToken": refresh_token})

    async def logout(self) -> dict:
        return await self.request("account/logout", {})

    async def close(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            await self.process.wait()
        for task in (self._reader, self._stderr_reader):
            if task and not task.done():
                task.cancel()


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def complete(self, model: str, instructions: str, user_text: str) -> str:
        payload = {
            "model": model,
            "instructions": instructions,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
            "store": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/responses",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
        if response.status_code >= 400:
            raise ProviderError(f"Provider returned HTTP {response.status_code}")
        data = response.json()
        texts = [c.get("text", "") for item in data.get("output", []) for c in item.get("content", []) if c.get("type") == "output_text"]
        answer = "".join(texts).strip()
        if not answer:
            raise ProviderError("Provider returned an empty response")
        return answer


class CodexSubscriptionProvider:
    """Experimental text-only adapter for a user-authorized ChatGPT subscription.

    Authentication is delegated to the official Codex app-server. Inference is a
    direct HTTPS request, so no Codex agent tools, shell or filesystem access are
    available to a phone call.
    """

    def __init__(
        self, codex_home: Path, app_server: CodexAppServer | None = None, timeout: int = 20
    ):
        self.codex_home = codex_home
        self.app_server = app_server
        self.timeout = timeout

    def _credentials(self) -> tuple[str, str]:
        path = self.codex_home / "auth.json"
        try:
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise ProviderError("Codex credential file permissions are too broad")
            data = json.loads(path.read_text())
        except ProviderError:
            raise
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderError("ChatGPT account is not connected") from exc
        tokens = data.get("tokens") or {}
        access_token = tokens.get("access_token") or data.get("access_token")
        account_id = (
            tokens.get("account_id")
            or tokens.get("chatgpt_account_id")
            or data.get("account_id")
        )
        if not access_token or not account_id:
            raise ProviderError("Codex credentials are incomplete")
        return access_token, account_id

    async def complete(
        self, model: str, instructions: str, user_text: str, effort: str = "none"
    ) -> str:
        if self.app_server:
            await self.app_server.account(refresh_token=True)
        access_token, account_id = self._credentials()
        payload = {
            "model": model,
            "instructions": instructions,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
            "reasoning": {"effort": effort},
            "store": False,
            "stream": True,
        }
        texts: list[str] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client, client.stream(
            "POST",
            "https://chatgpt.com/backend-api/codex/responses",
            headers={
                "Authorization": f"Bearer {access_token}",
                "ChatGPT-Account-Id": account_id,
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "User-Agent": "voice-agent-studio/0.1.0",
            },
            json=payload,
        ) as response:
            if response.status_code >= 400:
                raise ProviderError(f"Codex backend returned HTTP {response.status_code}")
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "response.output_text.delta":
                    texts.append(event.get("delta", ""))
        answer = "".join(texts).strip()
        if not answer:
            raise ProviderError("Codex returned an empty response")
        return answer
