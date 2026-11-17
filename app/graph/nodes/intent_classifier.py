from pydantic import BaseModel, Field
from app.graph.state import AgentState
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

class IntentClassifier(BaseModel):
    intent : str = Field(
        description="Intent of the user : 'faq', 'crm action', 'Human Escalation'"
    )
    
    tier : str = Field(
        description="Assigned tier: 'Tier-1' for faq, 'Tier-2' for crm action, 'Tier-3' for human escalation."
    )
    
    confidence: float = Field(
        description="Confidence score of this classification in range of 0.0 and 1.0"
    )

# Node function
def classify_intent_node(state:AgentState):
    ## Intent Classifier LLM
    llm = ChatOllama(model="llama3.1:8b", temperature=0.0)
    structured_llm = llm.with_structured_output(IntentClassifier)
    latest_message = state['messages'][-1].content
    ## Blank message 
    if not latest_message.strip():
        return{
            "intent":None,
            "curr_tier": "Unassigned",
            "confidence_score":0.0
        }

    system_prompt ="""You are the intent classifier and router for an enterprise agentic support system. 
Your role is to analyze the incoming customer message and classify it into the exact execution tier required by the downstream graph nodes.

### Classification Categories & Business Rules:

1. 'faq' (Tier-1)
   - Scope: General informational, policy, product feature, or how-to queries that can be answered using the FAQ knowledge base (RAG).
   - Criteria: Does NOT require querying customer databases, executing account changes, or modifying order states.

2. 'crm action' (Tier-2)
   - Scope: Requests requiring transactional database access or tool execution (e.g., CRM lookup, order status tracking, refund initiation, account updates).
   - Criteria: Customer is asking to retrieve or modify specific account/order data.

3. 'Human Escalation' (Tier-3)
   - Scope: Requests explicitly asking for a human representative, expressing severe anger/frustration, involving legal or safety concerns, or complex edge cases.


### Confidence Calibration Standards:
- High (0.90 - 1.00): Clear, unambiguous intent matching a single category.
- Medium (0.65 - 0.89): Request contains mild ambiguity or secondary questions, but primary intent is identifiable.
- Low (0.00 - 0.64): Vague, incomplete, conflicting, or corrupted input. (This triggers automatic Tier-3 escalation)."""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Coustomer message:\n {latest_message}")
    ]
    result = structured_llm.invoke(messages)
    return {
        "intent": result.intent,
        "curr_tier": result.tier,
        "confidence_score": result.confidence
    }
