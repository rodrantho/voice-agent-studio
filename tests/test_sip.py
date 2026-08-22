from voice_agent_studio.models import SipConfig
from voice_agent_studio.sip import render_asterisk


def test_asterisk_render_has_no_real_password():
    result = render_asterisk(SipConfig(host="pbx.example", extension="200", auth_username="agent"))
    assert "pbx.example" in result.pjsip
    assert "password=${ENV(VAS_SIP_PASSWORD)}" in result.pjsip
    assert "10000" in result.rtp
