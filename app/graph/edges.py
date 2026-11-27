from app.graph.state import AgentState


def route_intent(state: AgentState) -> str:
    intent = state.get("intent")
    confidence = state.get("confidence_score", 1.0)

    if confidence < 0.6:
        return "tier-3_human_escalation"

    if intent == "faq":
        return "tier-1_faq"
    elif intent == "crm action":
        return "tier-2_crm_action"
    elif intent == "Human Escalation":
        return "tier-3_human_escalation"

    return "tier-3_human_escalation"


def route_after_tier_2(state: AgentState) -> str:
    """Dynamically routes Tier-2 to Tier-3 if a Python guardrail triggered escalation."""
    if state.get("needs_escalation"):
        return "tier-3_human_escalation"
    return "end"