from __future__ import annotations

from dataclasses import dataclass

from .models import SipConfig


@dataclass
class AsteriskConfig:
    pjsip: str
    extensions: str
    rtp: str


def render_asterisk(config: SipConfig) -> AsteriskConfig:
    transport = f"transport-{config.transport}"
    endpoint = f"""[{transport}]
type=transport
protocol={config.transport}
bind=0.0.0.0:5060

[voice-agent-registration]
type=registration
outbound_auth=voice-agent-auth
server_uri=sip:{config.host}:{config.port}
client_uri=sip:{config.extension}@{config.host}:{config.port}
transport={transport}
retry_interval=60
forbidden_retry_interval=300
expiration=3600
contact_user={config.extension}

[voice-agent-auth]
type=auth
auth_type=userpass
username={config.auth_username or config.extension}
password=${{ENV(VAS_SIP_PASSWORD)}}

[voice-agent-endpoint]
type=endpoint
context=voice-agent-inbound
disallow=all
allow={','.join(config.codecs)}
outbound_auth=voice-agent-auth
aors=voice-agent-aor
transport={transport}

[voice-agent-aor]
type=aor
contact=sip:{config.host}:{config.port}

[voice-agent-identify]
type=identify
endpoint=voice-agent-endpoint
match={config.host}
"""
    extensions = """[voice-agent-inbound]
exten => _X!,1,NoOp(Voice Agent Studio inbound)
 same => n,Stasis(voice-agent-studio)
 same => n,Hangup()
"""
    rtp = f"[general]\nrtpstart={config.rtp_start}\nrtpend={config.rtp_end}\n"
    return AsteriskConfig(endpoint, extensions, rtp)
