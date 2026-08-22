from __future__ import annotations

import asyncio
import os
import shlex
import uuid
from pathlib import Path

import httpx

from .models import SpeechConfig


class SpeechError(RuntimeError):
    pass


class SpeechService:
    def __init__(self, config: SpeechConfig, stt_key: str | None, tts_key: str | None):
        self.config = config
        self.stt_key = stt_key
        self.tts_key = tts_key
        self.openai_base = os.environ.get("VAS_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.stt_model = os.environ.get("VAS_STT_MODEL", "gpt-4o-mini-transcribe")
        self.tts_model = os.environ.get("VAS_TTS_MODEL", "gpt-4o-mini-tts")
        self.timeout = int(os.environ.get("VAS_SPEECH_TIMEOUT", "45"))

    async def transcribe(self, audio_path: Path) -> str:
        if not audio_path.is_file() or audio_path.stat().st_size < 44:
            raise SpeechError("recording is missing or empty")
        if self.config.stt_provider == "openai":
            return await self._openai_stt(audio_path)
        if self.config.stt_provider == "deepgram":
            return await self._deepgram_stt(audio_path)
        command = os.environ.get("VAS_STT_COMMAND", "")
        if command:
            return await self._command_stt(command, audio_path)
        raise SpeechError("configured STT provider is not available; configure OpenAI, Deepgram or VAS_STT_COMMAND")

    async def synthesize(self, text: str, sounds_dir: Path) -> str:
        text = " ".join(text.split())[:2000]
        if not text:
            raise SpeechError("TTS text is empty")
        sounds_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        stem = f"vas-{uuid.uuid4().hex}"
        target = sounds_dir / f"{stem}.wav"
        if self.config.tts_provider == "openai":
            await self._openai_tts(text, target)
        elif self.config.tts_provider == "elevenlabs":
            await self._elevenlabs_tts(text, target)
        elif self.config.tts_provider == "piper":
            await self._piper_tts(text, target)
        else:
            raise SpeechError("unsupported TTS provider")
        await self._normalize(target)
        os.chmod(target, 0o640)
        return f"custom/{stem}"

    def _key(self, configured: str | None, provider: str) -> str:
        if configured:
            return configured
        raise SpeechError(f"{provider} API key is not configured")

    async def _openai_stt(self, path: Path) -> str:
        key = self._key(self.stt_key, "STT")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            with path.open("rb") as handle:
                response = await client.post(
                    f"{self.openai_base}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    data={"model": self.stt_model, "language": self.config.language.split("-")[0]},
                    files={"file": (path.name, handle, "audio/wav")},
                )
        if response.status_code >= 400:
            raise SpeechError(f"STT returned HTTP {response.status_code}")
        text = response.json().get("text", "").strip()
        if not text:
            raise SpeechError("STT returned an empty transcript")
        return text

    async def _deepgram_stt(self, path: Path) -> str:
        key = self._key(self.stt_key, "Deepgram")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://api.deepgram.com/v1/listen",
                params={"model": "nova-3", "language": self.config.language, "smart_format": "true"},
                headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav"},
                content=path.read_bytes(),
            )
        if response.status_code >= 400:
            raise SpeechError(f"Deepgram returned HTTP {response.status_code}")
        try:
            text = response.json()["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise SpeechError("Deepgram response did not contain a transcript") from exc
        if not text:
            raise SpeechError("STT returned an empty transcript")
        return text

    async def _command_stt(self, command: str, path: Path) -> str:
        args = [part.replace("{audio}", str(path)) for part in shlex.split(command)]
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), self.timeout)
        if process.returncode:
            raise SpeechError("external STT command failed")
        text = stdout.decode(errors="replace").strip()
        if not text:
            raise SpeechError("external STT returned an empty transcript")
        return text

    async def _openai_tts(self, text: str, target: Path) -> None:
        key = self._key(self.tts_key, "TTS")
        voice = self.config.voice or "alloy"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.openai_base}/audio/speech",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": self.tts_model, "voice": voice, "input": text, "response_format": "wav"},
            )
        if response.status_code >= 400:
            raise SpeechError(f"TTS returned HTTP {response.status_code}")
        target.write_bytes(response.content)

    async def _elevenlabs_tts(self, text: str, target: Path) -> None:
        key = self._key(self.tts_key, "ElevenLabs")
        voice = self.config.voice
        if not voice:
            raise SpeechError("ElevenLabs voice ID is not configured")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                params={"output_format": "pcm_16000"},
                headers={"xi-api-key": key},
                json={"text": text, "model_id": "eleven_multilingual_v2"},
            )
        if response.status_code >= 400:
            raise SpeechError(f"ElevenLabs returned HTTP {response.status_code}")
        raw = target.with_suffix(".pcm")
        raw.write_bytes(response.content)
        await self._ffmpeg(["-f", "s16le", "-ar", "16000", "-ac", "1", "-i", str(raw)], target)
        raw.unlink(missing_ok=True)

    async def _piper_tts(self, text: str, target: Path) -> None:
        model = os.environ.get("VAS_PIPER_MODEL", "")
        if not model:
            raise SpeechError("VAS_PIPER_MODEL is required for Piper TTS")
        command = shlex.split(os.environ.get("VAS_PIPER_COMMAND", "piper"))
        process = await asyncio.create_subprocess_exec(
            *command,
            "--model",
            model,
            "--output_file",
            str(target),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, _ = await asyncio.wait_for(process.communicate(text.encode()), self.timeout)
        if process.returncode:
            raise SpeechError("Piper TTS failed")

    async def _ffmpeg(self, input_args: list[str], target: Path) -> None:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            *input_args,
            "-ar",
            "8000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(target),
        )
        if await process.wait():
            raise SpeechError("ffmpeg audio conversion failed")

    async def _normalize(self, target: Path) -> None:
        converted = target.with_suffix(".normalized.wav")
        await self._ffmpeg(["-i", str(target)], converted)
        converted.replace(target)
