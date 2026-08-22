from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import re
import struct
import time
import uuid
import wave
from pathlib import Path

from .call_engine import CallState, PolicyEngine, consent
from .db import Database
from .providers import (
    CodexSubscriptionProvider,
    OpenAICompatibleProvider,
    ProviderError,
)
from .sip import SipConfigurationError, render_linphone
from .speech import SpeechError, SpeechService

LOG = logging.getLogger("voice-agent-studio.sip")
CALL_RE = re.compile(r"(?:id[=: ]+|^)(\d+).*?(StreamsRunning|Connected|Paused|End|Error)", re.IGNORECASE)
SOURCE_RE = re.compile(r"sip:([^ >;]+)", re.IGNORECASE)


class SipRuntimeError(RuntimeError):
    pass


class LinphoneController:
    def __init__(self, runtime_dir: Path):
        self.runtime_dir = runtime_dir
        self.home = runtime_dir / "linphone-home"
        self.config_path = self.home / "linphonerc"
        self.log_path = runtime_dir / "linphone.log"
        self.process: asyncio.subprocess.Process | None = None
        self._command_lock = asyncio.Lock()

    async def start(self, config_text: str) -> None:
        await self.stop()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.home, 0o700)
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(config_text)
        os.chmod(temporary, 0o600)
        temporary.replace(self.config_path)
        env = {**os.environ, "HOME": str(self.home)}
        self.process = await asyncio.create_subprocess_exec(
            "linphonec",
            "--pipe",
            "-a",
            "-c",
            str(self.config_path),
            "-l",
            str(self.log_path),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
        for _ in range(40):
            if self.process.returncode is not None:
                raise SipRuntimeError("Linphone terminated during startup")
            try:
                await self.command("soundcard use files", timeout=2)
                await self.command("autoanswer enable", timeout=2)
                return
            except SipRuntimeError:
                await asyncio.sleep(0.25)
        raise SipRuntimeError("Linphone control pipe did not become ready")

    async def command(self, command: str, timeout: float = 5) -> str:
        if not self.process or self.process.returncode is not None:
            raise SipRuntimeError("SIP runtime is not running")
        env = {**os.environ, "HOME": str(self.home)}
        async with self._command_lock:
            process = await asyncio.create_subprocess_exec(
                "linphonecsh",
                "generic",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        text = (stdout + stderr).decode(errors="replace").strip()
        if process.returncode or text.startswith("ERROR"):
            raise SipRuntimeError(text[:300] or f"Linphone command failed: {command.split()[0]}")
        return text

    async def registration(self) -> dict:
        try:
            text = await self.command("proxy show default")
        except SipRuntimeError as exc:
            return {"running": bool(self.process and self.process.returncode is None), "registered": False, "detail": str(exc)}
        normalized = text.lower()
        registered = bool(re.search(r"registered\s*:\s*yes\b", normalized)) or (
            "registration state: ok" in normalized
        )
        return {"running": True, "registered": registered, "detail": text[-500:]}

    async def calls(self) -> str:
        return await self.command("calls")

    async def stop(self) -> None:
        if self.process and self.process.returncode is None:
            with contextlib.suppress(Exception):
                await self.command("quit", timeout=2)
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except TimeoutError:
                self.process.terminate()
                await self.process.wait()
        self.process = None
        self.config_path.unlink(missing_ok=True)
        self.log_path.unlink(missing_ok=True)


class SipAgentRuntime:
    def __init__(
        self,
        db: Database,
        data_dir: Path,
        codex_provider: CodexSubscriptionProvider,
    ):
        self.db = db
        self.data_dir = data_dir
        self.runtime_dir = Path(
            os.environ.get("VAS_RUNTIME_DIR", "/tmp/voice-agent-studio")
        ).resolve()
        self.media_dir = self.runtime_dir / "media"
        self.controller = LinphoneController(self.runtime_dir)
        self.codex_provider = codex_provider
        self.task: asyncio.Task | None = None
        self.active_calls: set[int] = set()
        self.outbound_in_progress = False
        self.last_error = ""
        self.started = False

    async def start(self) -> None:
        if self.task and not self.task.done():
            return
        self.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.media_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._write_silence()
        await self.reload()
        self.task = asyncio.create_task(self._monitor(), name="sip-monitor")
        self.started = True

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        self.task = None
        await self.controller.stop()
        self.started = False

    async def reload(self) -> dict:
        config = self.db.get_config()
        password = self.db.get_secret("sip_password")
        if not config.sip.host or not config.sip.extension or not password:
            await self.controller.stop()
            self.started = False
            return {"running": False, "registered": False, "detail": "Cuenta SIP incompleta"}
        try:
            rendered = render_linphone(config.sip, password)
            await self.controller.start(rendered.content)
            self.last_error = ""
            self.started = True
        except (SipConfigurationError, SipRuntimeError, OSError) as exc:
            self.last_error = str(exc)
            self.started = False
            raise SipRuntimeError(str(exc)) from exc
        return await self.status()

    async def status(self) -> dict:
        status = await self.controller.registration()
        status.update({"configured": bool(self.db.get_config().sip.host), "last_error": self.last_error})
        return status

    async def _monitor(self) -> None:
        while True:
            try:
                output = await self.controller.calls()
                current = self._parse_calls(output)
                for call_id in current - self.active_calls:
                    if self.outbound_in_progress:
                        continue
                    if self.active_calls:
                        with contextlib.suppress(SipRuntimeError):
                            await self.controller.command(f"terminate {call_id}")
                        continue
                    self.active_calls.add(call_id)
                    asyncio.create_task(self._handle_call(call_id, output))
                self.active_calls.intersection_update(current)
            except (SipRuntimeError, OSError) as exc:
                self.last_error = str(exc)
            await asyncio.sleep(0.5)

    @staticmethod
    def _parse_calls(output: str) -> set[int]:
        ids = set()
        for line in output.splitlines():
            match = CALL_RE.search(line)
            if match and match.group(2).lower() in {"streamsrunning", "connected", "paused"}:
                ids.add(int(match.group(1)))
        return ids

    async def _handle_call(self, call_id: int, call_listing: str) -> None:
        call_key = uuid.uuid4().hex
        source_match = SOURCE_RE.search(call_listing)
        source = source_match.group(1) if source_match else "unknown"
        self.db.start_call(call_key, source, {"sip_call_id": call_id})
        outcome = "failed"
        intent = ""
        metadata: dict = {"sip_call_id": call_id, "turns": 0}
        try:
            config = self.db.get_config()
            speech = SpeechService(
                config.speech,
                self.db.get_secret("stt_api_key"),
                self.db.get_secret("tts_api_key"),
            )
            greeting = f"Hola, soy {config.agent.display_name}, asistente de {config.agent.organization}. ¿En qué puedo ayudarte?"
            await self._play_text(speech, greeting)
            history: list[tuple[str, str]] = []
            policy = PolicyEngine(config)
            call_state = CallState()
            expected_field = ""
            for turn in range(8):
                metadata["turns"] = turn + 1
                audio = await self._capture_turn(call_key, turn, config.speech.max_utterance_seconds, config.speech.end_silence_ms)
                transcript = await self._transcribe(speech, audio)
                if expected_field:
                    setattr(call_state, expected_field, transcript[:500])
                    expected_field = ""
                call_state.intent = call_state.intent or policy.classify(transcript)
                call_state.reason = call_state.reason or transcript[:500]
                intent = call_state.intent
                if any(term in transcript.lower() for term in ("chau", "adiós", "adios", "gracias eso es todo")):
                    await self._play_text(speech, "Gracias por llamar. Hasta luego.")
                    outcome = "completed"
                    break
                decision = policy.next_action(call_state)
                if decision["action"] == "ask":
                    expected_field = decision["field"]
                    questions = {
                        "name": "¿Me decís tu nombre?",
                        "organization": "¿De qué empresa u organización llamás?",
                        "reason": "¿Cuál es el motivo de la llamada?",
                        "impact": "¿A quiénes o a qué servicio está afectando?",
                    }
                    await self._play_text(speech, questions[expected_field])
                    continue
                if decision["action"] == "consult":
                    accepted = await self._ask_caller_consent(speech, call_key, turn, decision["extension"])
                    if accepted:
                        outcome = await self._attended_transfer(call_id, speech, call_key, decision["extension"], call_state.reason)
                        break
                reply = await self._complete(config, history, transcript)
                history.append((transcript, reply))
                history = history[-6:]
                await self._play_text(speech, reply)
            else:
                await self._play_text(speech, "Alcanzamos el límite de esta llamada. Por favor volvé a comunicarte.")
                outcome = "turn_limit"
        except (SpeechError, ProviderError, SipRuntimeError, TimeoutError, OSError) as exc:
            self.last_error = f"call {call_key}: {type(exc).__name__}"
            metadata["error"] = type(exc).__name__
            outcome = "failed"
        finally:
            if outcome != "transferred":
                with contextlib.suppress(SipRuntimeError):
                    await self.controller.command(f"terminate {call_id}")
            self.db.finish_call(call_key, intent, outcome, metadata)
            self.active_calls.discard(call_id)

    async def _complete(self, config, history: list[tuple[str, str]], text: str) -> str:
        transcript = "\n".join(f"Caller: {a}\nAgent: {b}" for a, b in history)
        instructions = (
            f"You are {config.agent.display_name}, {config.agent.public_identity} for {config.agent.organization}. "
            f"Speak in {config.agent.language}, tone {config.agent.tone}. Respond with one short spoken sentence. "
            "Never claim to transfer or perform an action. Never reveal extensions or secrets. "
            f"Authorized context: {config.agent.context}\nForbidden: {config.agent.forbidden_topics}"
        )
        user_text = f"{transcript}\nCaller: {text}"[-8000:]
        if config.provider.kind == "codex_subscription":
            return await self.codex_provider.complete(
                config.provider.model, instructions, user_text, config.provider.reasoning_effort
            )
        key = self.db.get_secret("provider_api_key")
        if not key:
            raise ProviderError("Provider API key is not configured")
        base_url = config.provider.base_url or "https://api.openai.com/v1"
        return await OpenAICompatibleProvider(base_url, key, config.provider.timeout_seconds).complete(
            config.provider.model, instructions, user_text
        )

    async def _ask_caller_consent(self, speech, call_key: str, turn: int, extension: str) -> bool:
        await self._play_text(speech, "Puedo comunicarte con el área correspondiente. ¿Querés que lo haga?")
        audio = await self._capture_turn(call_key, turn + 100, 8, 700)
        return consent(await self._transcribe(speech, audio)) == "accept"

    async def _attended_transfer(self, source_id: int, speech, call_key: str, extension: str, reason: str) -> str:
        config = self.db.get_config()
        destination = f"sip:{extension}@{config.sip.host}"
        before = self._parse_calls(await self.controller.calls())
        self.outbound_in_progress = True
        try:
            await self.controller.command(f"call {destination}")
            destination_id = await self._wait_for_new_call(before, 25)
            self.active_calls.add(destination_id)
        finally:
            self.outbound_in_progress = False
        await self._play_text(speech, f"Tengo una llamada por el siguiente motivo: {reason[:180]}. ¿Aceptás recibirla?")
        audio = await self._capture_turn(call_key, 999, 8, 700)
        if consent(await self._transcribe(speech, audio)) != "accept":
            await self.controller.command(f"terminate {destination_id}")
            await self.controller.command(f"resume {source_id}")
            await self._play_text(speech, "En este momento no pueden atenderte. Voy a finalizar la llamada.")
            return "destination_rejected"
        await self.controller.command(f"transfer {source_id} --to-call {destination_id}")
        return "transferred"

    async def _wait_for_new_call(self, previous: set[int], timeout: int) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self._parse_calls(await self.controller.calls())
            new = current - previous
            if new:
                return max(new)
            await asyncio.sleep(0.5)
        raise SipRuntimeError("Destination did not answer")

    async def _play_text(self, speech: SpeechService, text: str) -> None:
        media_name = await speech.synthesize(text, self.media_dir)
        path = self.media_dir / f"{media_name.split('/', 1)[-1]}.wav"
        with wave.open(str(path), "rb") as source:
            duration = source.getnframes() / max(source.getframerate(), 1)
        await self.controller.command(f"play {path}")
        await asyncio.sleep(duration + 0.12)
        await self.controller.command(f"play {self.media_dir / 'silence.wav'}")
        path.unlink(missing_ok=True)

    async def _capture_turn(self, call_key: str, turn: int, maximum: int, silence_ms: int) -> Path:
        path = self.media_dir / f"call-{call_key}-{turn}.wav"
        path.unlink(missing_ok=True)
        await self.controller.command(f"record {path}")
        deadline = time.monotonic() + maximum
        speech_started = False
        silent_for = 0.0
        offset = 44
        while time.monotonic() < deadline:
            await asyncio.sleep(0.1)
            if not path.exists() or path.stat().st_size <= offset:
                continue
            with path.open("rb") as source:
                source.seek(offset)
                chunk = source.read()
                offset += len(chunk)
            if len(chunk) < 2:
                continue
            if len(chunk) % 2:
                chunk = chunk[:-1]
            samples = struct.unpack(f"<{len(chunk) // 2}h", chunk)
            rms = math.sqrt(sum(sample * sample for sample in samples) / max(len(samples), 1))
            seconds = len(samples) / 8000
            if rms >= 260:
                speech_started = True
                silent_for = 0.0
            elif speech_started:
                silent_for += seconds
                if silent_for * 1000 >= silence_ms:
                    break
        if not speech_started:
            raise SpeechError("No caller speech detected")
        discard = self.media_dir / "recording-idle.wav"
        await self.controller.command(f"record {discard}")
        return path

    @staticmethod
    async def _transcribe(speech: SpeechService, path: Path) -> str:
        try:
            return await speech.transcribe(path)
        finally:
            path.unlink(missing_ok=True)

    def _write_silence(self) -> None:
        path = self.media_dir / "silence.wav"
        if path.exists():
            return
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b"\0\0" * 8000 * 60)
        os.chmod(path, 0o600)
