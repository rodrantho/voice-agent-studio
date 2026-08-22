import pytest
from pydantic import ValidationError

from voice_agent_studio.models import AppConfig, DirectoryEntry, RoutingRule, SipConfig


def test_safe_defaults():
    config = AppConfig()
    assert config.safety.require_destination_acceptance
    assert config.safety.fail_closed_on_ambiguous_consent
    assert not config.safety.allow_external_calls
    assert not config.safety.allow_model_tools
    assert not config.safety.record_calls


def test_rejects_bad_rtp_range():
    with pytest.raises(ValidationError):
        SipConfig(rtp_start=20000, rtp_end=10000)


def test_directory_ids_are_restricted():
    with pytest.raises(ValidationError):
        DirectoryEntry(id="../../secret", name="Bad", extension="1")


def test_route_must_reference_allowlisted_destination():
    with pytest.raises(ValidationError):
        AppConfig(
            routing=[
                RoutingRule(
                    id="bad_route", name="Bad", intent="general", destination_id="missing"
                )
            ]
        )


@pytest.mark.parametrize("field", ["host", "extension", "auth_username"])
def test_sip_fields_reject_config_injection(field):
    with pytest.raises(ValidationError):
        SipConfig(**{field: "valid\n[malicious]"})
