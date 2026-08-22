from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator


class BusinessHours(BaseModel):
    timezone: str = "UTC"
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    opens: str = "09:00"
    closes: str = "18:00"


class AgentProfile(BaseModel):
    display_name: str = Field(default="Assistant", max_length=100)
    organization: str = Field(default="My organization", max_length=150)
    language: str = "en-US"
    public_identity: str = "Virtual assistant"
    audience: Literal["customers", "employees", "both"] = "customers"
    tone: Literal["formal", "neutral", "friendly"] = "friendly"
    unknown_behavior: Literal["take_message", "transfer", "end_call"] = "take_message"
    context: str = Field(default="", max_length=10000)
    forbidden_topics: str = Field(default="", max_length=4000)
    hours: BusinessHours = Field(default_factory=BusinessHours)


class SipConfig(BaseModel):
    host: str = Field(default="", max_length=253, pattern=r"^$|^[A-Za-z0-9][A-Za-z0-9.:-]*$")
    port: int = Field(default=5060, ge=1, le=65535)
    transport: Literal["udp", "tcp"] = "udp"
    extension: str = Field(
        default="", max_length=64, pattern=r"^$|^[A-Za-z0-9][A-Za-z0-9_.+*-]*$"
    )
    auth_username: str = Field(
        default="", max_length=128, pattern=r"^$|^[A-Za-z0-9][A-Za-z0-9_.@+*-]*$"
    )
    codecs: list[Literal["ulaw", "alaw", "g722", "opus"]] = Field(
        default_factory=lambda: ["ulaw", "alaw"]
    )
    local_port: int = Field(default=5062, ge=1024, le=65535)
    rtp_start: int = Field(default=10000, ge=1024, le=65535)
    rtp_end: int = Field(default=10100, ge=1024, le=65535)

    @field_validator("rtp_end")
    @classmethod
    def valid_range(cls, value: int, info):
        start = info.data.get("rtp_start", 10000)
        if value < start:
            raise ValueError("rtp_end must be greater than or equal to rtp_start")
        return value


class ProviderConfig(BaseModel):
    kind: Literal["codex_subscription", "openai_api", "openai_compatible"] = "codex_subscription"
    model: str = Field(default="", max_length=128, pattern=r"^[A-Za-z0-9._:/-]*$")
    base_url: str = Field(default="", max_length=2048)
    reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    timeout_seconds: int = Field(default=20, ge=2, le=120)
    fallback_enabled: bool = False

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value: str):
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an HTTP(S) URL")
        if parsed.username or parsed.password or "\n" in value or "\r" in value:
            raise ValueError("base_url must not contain credentials or control characters")
        return value.rstrip("/")


class SpeechConfig(BaseModel):
    stt_provider: Literal["google_web", "openai", "deepgram"] = "openai"
    tts_provider: Literal["piper", "openai", "elevenlabs"] = "openai"
    voice: str = ""
    language: str = "en-US"
    end_silence_ms: int = Field(default=600, ge=200, le=3000)
    max_utterance_seconds: int = Field(default=20, ge=3, le=120)


class DirectoryEntry(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str
    extension: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.+*-]*$"
    )
    aliases: list[str] = Field(default_factory=list)
    area: str = ""
    customer_visible: bool = True
    transfer_allowed: bool = True
    acceptance_required: bool = True
    timeout_seconds: int = Field(default=20, ge=5, le=120)
    fallback_ids: list[str] = Field(default_factory=list)


class RoutingRule(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str
    intent: str
    destination_id: str
    required_fields: list[Literal["name", "organization", "reason", "impact"]] = Field(
        default_factory=lambda: ["name", "organization", "reason"]
    )
    enabled: bool = True


class SafetyRules(BaseModel):
    require_destination_acceptance: bool = True
    fail_closed_on_ambiguous_consent: bool = True
    expose_extensions: bool = False
    allow_external_calls: bool = False
    allow_model_tools: bool = False
    record_calls: bool = False
    retain_transcripts: bool = False
    deterministic_fallback: bool = True


class AppConfig(BaseModel):
    schema_version: int = 1
    configured: bool = False
    agent: AgentProfile = Field(default_factory=AgentProfile)
    sip: SipConfig = Field(default_factory=SipConfig)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    directory: list[DirectoryEntry] = Field(default_factory=list)
    routing: list[RoutingRule] = Field(default_factory=list)
    safety: SafetyRules = Field(default_factory=SafetyRules)

    @model_validator(mode="after")
    def validate_references(self):
        destination_ids = [entry.id for entry in self.directory]
        if len(destination_ids) != len(set(destination_ids)):
            raise ValueError("directory IDs must be unique")
        known = set(destination_ids)
        for entry in self.directory:
            unknown = set(entry.fallback_ids) - known
            if unknown:
                raise ValueError(f"unknown fallback destination(s): {sorted(unknown)}")
            if entry.id in entry.fallback_ids:
                raise ValueError(f"destination {entry.id} cannot fall back to itself")
        rule_ids = [rule.id for rule in self.routing]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("routing rule IDs must be unique")
        for rule in self.routing:
            if rule.destination_id not in known:
                raise ValueError(f"routing rule {rule.id} references an unknown destination")
        return self


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    username: str
    password: str


class SecretInput(BaseModel):
    name: Literal["sip_password", "provider_api_key", "stt_api_key", "tts_api_key"]
    value: str = Field(min_length=1, max_length=8192)


class SimulationRequest(BaseModel):
    utterance: str = Field(min_length=1, max_length=2000)
    state: dict[str, str] = Field(default_factory=dict)


class SpeechTestRequest(BaseModel):
    text: str = Field(default="Voice Agent Studio audio test.", min_length=1, max_length=500)
