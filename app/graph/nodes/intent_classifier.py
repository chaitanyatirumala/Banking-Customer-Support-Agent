from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from app.graph.state import AgentState


class IntentClassifier(BaseModel):
    intent: Literal["faq", "crm action", "Human Escalation"] = Field(
        description="Exact intent of the user: 'faq', 'crm action', or 'Human Escalation'."
    )
    tier: Literal["Tier-1", "Tier-2", "Tier-3"] = Field(
        description="Assigned tier: 'Tier-1' for faq, 'Tier-2' for crm action, 'Tier-3' for Human Escalation."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score of this classification between 0.0 and 1.0.",
    )
    reasoning: str = Field(
        description="One-sentence justification for the chosen intent."
    )


def classify_intent_node(state: AgentState) -> dict:
    """Classifies customer messages into Tier-1 (RBI FAQ), Tier-2 (Transactions), or Tier-3 (Escalation)."""
    latest_message = state["messages"][-1].content

    # Edge-case guardrail: Intercept blank input before calling the LLM
    if not latest_message.strip():
        return {
            "intent": None,
            "curr_tier": "Unassigned",
            "confidence_score": 0.0,
            "needs_escalation": True,
            "escalation_reason": "Blank or empty message received from customer.",
        }

    llm = ChatOllama(model="llama3.1:8b", temperature=0.0)
    structured_llm = llm.with_structured_output(IntentClassifier)

    system_prompt = """You are the intent classifier and router for an Indian Fintech UPI & Card Dispute Resolution Agent.
Analyze the incoming customer message and classify it into the exact execution tier required by the downstream graph nodes.

### Classification Categories & Business Rules:

1. 'faq' (Tier-1)
   - Scope: General policy questions about RBI T+1 UPI auto-reversal rules, ₹100/day delay compensation, bank chargeback timelines, or refund eligibility policies.
   - Criteria: Does NOT ask to look up a specific transaction or process a refund.

2. 'crm action' (Tier-2)
   - Scope: Requests involving specific UPI or Card transactions (e.g., UPI-9001), listing recent transactions, checking merchant settlement status, or requesting a refund for a failed or duplicate debit.
   - Criteria: Requires querying the transactions database or calling a refund tool.

3. 'Human Escalation' (Tier-3)
   - Scope: Suspected fraud, stolen/compromised card or UPI account, unauthorized transactions, international card disputes, severe distress, or explicit requests for a Risk & Compliance Officer / human agent.

### Confidence Calibration Standards:
- High (0.90 - 1.00): Clear, unambiguous intent matching a single category.
- Medium (0.65 - 0.89): Mild ambiguity, but primary intent is identifiable.
- Low (0.00 - 0.64): Vague, incomplete, conflicting, or corrupted input (triggers automatic Tier-3 escalation)."""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Customer message:\n{latest_message}"),
    ]

    result: IntentClassifier = structured_llm.invoke(messages)

    print(
        f"[CLASSIFIER] -> Intent: {result.intent} | Tier: {result.tier} | "
        f"Confidence: {result.confidence:.2f} | Reason: {result.reasoning}"
    )

    is_direct_escalation = (
        result.intent == "Human Escalation" or result.confidence < 0.60
    )

    return {
        "intent": result.intent,
        "curr_tier": result.tier,
        "confidence_score": result.confidence,
        "needs_escalation": is_direct_escalation,
        "escalation_reason": result.reasoning if is_direct_escalation else None,
    }