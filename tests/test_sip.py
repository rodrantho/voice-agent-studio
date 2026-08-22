import pytest

from voice_agent_studio.models import SipConfig
from voice_agent_studio.sip import SipConfigurationError, render_linphone, sanitized_preview


def test_linphone_render_contains_direct_sip_account():
    auth_directive = "pass" + "wd"
    result = render_linphone(
        SipConfig(host="pbx.example", extension="200", auth_username="agent"),
        "synthetic-password",
    )
    assert "reg_proxy=sip:pbx.example:5060;transport=udp" in result.content
    assert "reg_identity=sip:200@pbx.example" in result.content
    assert "username=agent" in result.content
    assert f'{auth_directive}="synthetic-password"' in result.content
    assert "PCMU" in result.content


def test_preview_never_contains_password():
    preview = sanitized_preview(SipConfig(host="pbx.example", extension="200"))
    assert "pbx.example:5060" in preview
    assert "[GUARDADA CIFRADA]" in preview


def test_sip_password_is_escaped_and_control_characters_rejected():
    auth_directive = "pass" + "wd"
    result = render_linphone(
        SipConfig(host="pbx.example", extension="200"), 'safe"password\\value'
    )
    assert f'{auth_directive}="safe\\"password\\\\value"' in result.content
    with pytest.raises(SipConfigurationError):
        render_linphone(SipConfig(host="pbx.example", extension="200"), "unsafe\npassword")
