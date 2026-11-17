from app.graph.state import AgentState
def route_intent(state:AgentState):
    intent = state.get("intent")
    confidence = state.get("confidence_score",1.0)

    if confidence < 0.6:
        return "tier_3_human_escalation"

    if intent == "faq":
        return "tier-1_faq"
    elif intent == "crm action":
        return "tier-2_crm_action"
    elif intent == "human Escalation":
        return "tier-3_human_escalation"

    # fallback for unexpected LLM behaviour
    return "tier-3_human_escalation"