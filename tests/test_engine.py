from voice_agent_studio.call_engine import PolicyEngine, consent
from voice_agent_studio.models import AppConfig, DirectoryEntry, RoutingRule


def configured():
    return AppConfig(
        directory=[DirectoryEntry(id="support", name="Support", extension="200")],
        routing=[RoutingRule(id="support_rule", name="Support", intent="support", destination_id="support")],
    )


def test_policy_collects_required_fields_before_transfer():
    engine = PolicyEngine(configured())
    result = engine.simulate("Internet support issue", {})
    assert result["state"]["intent"] == "support"
    assert result["next"] == {"action": "ask", "field": "name"}


def test_policy_routes_only_after_required_fields():
    engine = PolicyEngine(configured())
    result = engine.simulate("Internet support issue", {"name": "Alex", "organization": "Example", "impact": "one user"})
    assert result["next"]["action"] == "consult"
    assert result["next"]["extension"] == "200"
    assert result["next"]["acceptance_required"] is True


def test_consent_fails_closed_and_negative_wins():
    assert consent("sí, dale") == "accept"
    assert consent("sí, pero no puedo") == "reject"
    assert consent("tal vez") == "ambiguous"
    assert consent("bueno, veamos") == "ambiguous"
