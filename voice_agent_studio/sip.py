from __future__ import annotations

from dataclasses import dataclass

from .models import SipConfig


class SipConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class LinphoneConfig:
    content: str
    identity: str
    proxy: str


def _safe(value: str, field: str) -> str:
    if not value or any(char in value for char in "\r\n[]"):
        raise SipConfigurationError(f"invalid {field}")
    return value


def render_linphone(config: SipConfig, password: str) -> LinphoneConfig:
    host = _safe(config.host, "SIP host")
    extension = _safe(config.extension, "SIP extension")
    auth_username = _safe(config.auth_username or extension, "SIP auth username")
    password = _safe(password, "SIP password")
    transport = config.transport.lower()
    proxy = f"sip:{host}:{config.port};transport={transport}"
    identity = f"sip:{extension}@{host}"
    escaped_password = password.replace("\\", "\\\\").replace('"', '\\"')
    codec_names = {"ulaw": "PCMU", "alaw": "PCMA", "g722": "G722", "opus": "opus"}
    enabled = {codec_names[name].lower() for name in config.codecs}
    codecs = [
        (0, "PCMU", 8000),
        (8, "PCMA", 8000),
        (9, "G722", 8000),
        (111, "opus", 48000),
    ]
    payloads = []
    for index, (number, mime, rate) in enumerate(codecs):
        payloads.append(
            f"[audio_codec_{index}]\nmime={mime}\nrate={rate}\nchannels=1\n"
            f"recv_fmtp=\nenabled={1 if mime.lower() in enabled else 0}\nnumber={number}\n"
        )
    content = f"""[net]
download_bw=0
upload_bw=0
firewall_policy=0

[sip]
sip_port={config.local_port}
guess_hostname=1
inc_timeout=30
use_info=1
use_rfc2833=1
default_proxy=0

[rtp]
audio_rtp_port={config.rtp_start}
audio_jitt_comp=60

[sound]
playback_dev_id=ALSA: default device
ringer_dev_id=ALSA: default device
capture_dev_id=ALSA: default device

[proxy_0]
reg_proxy={proxy}
reg_route=
reg_identity={identity}
reg_expires=3600
reg_sendregister=1
publish=0
dial_escape_plus=0

[auth_info_0]
username={auth_username}
userid={auth_username}
passwd=\"{escaped_password}\"
realm=
domain={host}

""" + "\n".join(payloads)
    return LinphoneConfig(content=content, identity=identity, proxy=proxy)


def sanitized_preview(config: SipConfig) -> str:
    if not config.host or not config.extension:
        return "Cuenta SIP incompleta."
    auth = config.auth_username or config.extension
    codecs = ", ".join(config.codecs)
    return (
        f"Servidor: {config.host}:{config.port} ({config.transport.upper()})\n"
        f"Interno: {config.extension}\n"
        f"Usuario de autenticación: {auth}\n"
        f"Puerto SIP local: {config.local_port}\n"
        f"RTP: {config.rtp_start}-{config.rtp_end}\n"
        f"Codecs: {codecs}\n"
        "Contraseña: [GUARDADA CIFRADA]"
    )
