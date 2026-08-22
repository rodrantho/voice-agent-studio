from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from .models import AppConfig, RoutingRule

StateName = Literal["received", "collecting", "consulting", "transferring", "message", "completed"]


@dataclass
class CallState:
    state: StateName = "received"
    intent: str = ""
    name: str = ""
    organization: str = ""
    reason: str = ""
    impact: str = ""
    destination_id: str = ""
    events: list[str] = field(default_factory=list)


class PolicyEngine:
    def __init__(self, config: AppConfig):
        self.config = config

    def classify(self, utterance: str) -> str:
        normalized = " ".join(utterance.lower().split())
        for rule in self.config.routing:
            if rule.enabled and (rule.intent.lower() in normalized or rule.name.lower() in normalized):
                return rule.intent
        if any(term in normalized for term in ("support", "technical", "internet", "server", "soporte", "técnico", "internet", "servidor")):
            return "support"
        if any(term in normalized for term in ("sales", "quote", "ventas", "presupuesto")):
            return "sales"
        return "general"

    def route(self, state: CallState) -> RoutingRule | None:
        return next((r for r in self.config.routing if r.enabled and r.intent == state.intent), None)

    def next_action(self, state: CallState) -> dict:
        rule = self.route(state)
        if not rule:
            return {"action": "take_message", "reason": "no_matching_route"}
        for required in rule.required_fields:
            if not getattr(state, required, ""):
                return {"action": "ask", "field": required}
        destination = next((d for d in self.config.directory if d.id == rule.destination_id and d.transfer_allowed), None)
        if not destination:
            return {"action": "take_message", "reason": "destination_unavailable"}
        return {
            "action": "consult",
            "destination_id": destination.id,
            "extension": destination.extension,
            "acceptance_required": destination.acceptance_required,
        }

    def simulate(self, utterance: str, supplied: dict[str, str]) -> dict:
        state = CallState(**{k: v for k, v in supplied.items() if k in CallState.__dataclass_fields__})
        state.intent = state.intent or self.classify(utterance)
        if not state.reason:
            state.reason = utterance[:500]
        action = self.next_action(state)
        return {"state": state.__dict__, "next": action}


def consent(text: str) -> Literal["accept", "reject", "ambiguous"]:
    normalized = " ".join(re.sub(r"[^a-záéíóúüñ0-9 ]", " ", text.lower()).split())
    padded = f" {normalized} "
    negatives = ("no", "nunca", "no puedo", "ocupado", "después", "mas tarde", "más tarde")
    positives = ("sí", "si", "acepto", "dale", "ok", "bien", "claro", "pasámelo", "pasamela")
    if any(f" {phrase} " in padded for phrase in negatives):
        return "reject"
    if any(f" {phrase} " in padded for phrase in positives):
        return "accept"
    return "ambiguous"
