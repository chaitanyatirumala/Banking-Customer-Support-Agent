from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from app.graph.state import AgentState
from app.tools.crm_db import CRM_TOOLS
from app.tools.faq_rag import retrieve_faq
from app.utils.escalation_token import create_escalation_token

# Fixed: dictionary mapping tool name -> actual LangChain tool object
TOOL_MAP = {tool.name: tool for tool in CRM_TOOLS}


def tier_1_rag_node(state: AgentState) -> dict:
    print("\n[SYSTEM] -> Routing to Tier 1 (RBI & Bank Policy RAG)...")
    user_question = state["messages"][-1].content
    relevant_rules = retrieve_faq(user_question)

    llm = ChatOllama(model="llama3.1:8b", temperature=0.0)
    prompt = (
        "You are a Tier-1 Indian Fintech UPI & Card dispute support assistant. "
        "Answer the customer's question strictly using the RBI and bank rules below. "
        "Keep your answer concise and easy to understand.\n\n"
        f"RBI & Bank Rules:\n{relevant_rules}\n\n"
        f"Customer Question: {user_question}"
    )

    response = llm.invoke(prompt)
    return {
        "curr_tier": "tier_1_rag",
        "messages": [AIMessage(content=response.content)],
    }


def tier_2_crm_action(state: AgentState) -> dict:
    print("\n[SYSTEM] -> Routing to Tier 2 (UPI/Card Transaction Tools)...")
    user_query = state["messages"][-1].content
    customer_id = state["customer_id"]

    llm = ChatOllama(model="llama3.1:8b", temperature=0.0)
    llm_with_tools = llm.bind_tools(CRM_TOOLS)

    messages = [
        SystemMessage(
            content=(
                f"You are a Tier-2 Indian Fintech dispute agent. The logged-in customer_id is '{customer_id}'. "
                "Use the provided tools to list recent transactions, verify UPI/Card status, "
                "or attempt an instant refund for failed/duplicate debits."
            )
        ),
        HumanMessage(content=user_query),
    ]

    ai_decision = llm_with_tools.invoke(messages)

    if ai_decision.tool_calls:
        tool_call = ai_decision.tool_calls[0]
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        print(f"[CRM AGENT] -> Calling tool '{tool_name}' with args: {tool_args}")

        if tool_name not in TOOL_MAP:
            return {
                "curr_tier": "tier_2_crm",
                "needs_escalation": True,
                "escalation_reason": f"Agent requested an unknown tool: {tool_name}",
            }

        selected_tool = TOOL_MAP[tool_name]
        db_result = str(selected_tool.invoke(tool_args))
        print(f"[CRM DB]    -> Result: {db_result}")

        # Deterministic Guardrail Check: Hand off directly to Tier-3 if blocked
        if db_result.startswith("ESCALATE_TIER_3:"):
            print("[GUARDRAIL] -> Hard policy limit triggered! Escalating Tier-2 -> Tier-3...")
            return {
                "curr_tier": "tier_2_crm",
                "needs_escalation": True,
                "escalation_reason": db_result,
            }

        final_prompt = (
            f"Customer asked: {user_query}\n"
            f"Bank database returned: {db_result}\n"
            "Write a short, clear, polite reply to the customer using this exact database result."
        )
        final_reply = llm.invoke(final_prompt)
        reply_text = final_reply.content
    else:
        reply_text = (
            ai_decision.content
            or "Could you please share your Transaction ID (e.g., UPI-9001) so I can check your payment?"
        )

    return {
        "curr_tier": "tier_2_crm",
        "needs_escalation": False,
        "messages": [AIMessage(content=reply_text)],
    }


def tier_3_human_node(state: AgentState) -> dict:
    print("\n[SYSTEM] -> Routing to Tier 3 (Risk & Compliance Async Escalation)...")
    customer_id = state["customer_id"]
    reason = state.get("escalation_reason") or "Flagged for Risk & Compliance Officer review."

    # 1. Build a clean text transcript for the compliance audit record
    transcript = [
        f"{'Customer' if isinstance(m, HumanMessage) else 'Agent'}: {m.content}"
        for m in state["messages"]
    ]

    # 2. Generate a concise pre-filled audit summary for the Compliance Officer
    llm = ChatOllama(model="llama3.1:8b", temperature=0.0)
    summary_prompt = (
        "You are a bank compliance analyst assistant. Write a concise 3-bullet audit summary "
        "(Transaction/Issue, Triggered Policy Rule, Recommended Officer Check) for a Risk & Compliance Officer.\n\n"
        f"Customer ID: {customer_id}\n"
        f"Escalation Trigger: {reason}\n"
        f"Transcript:\n" + "\n".join(transcript)
    )
    handoff_summary = llm.invoke(summary_prompt).content

    # 3. Persist PII in SQLite and mint a zero-PII 24-hour JWT reference token
    ticket_info = create_escalation_token(
        customer_id=customer_id,
        escalation_reason=reason,
        audit_summary=handoff_summary,
        conversation_transcript=transcript,
    )

    print(f"[TIER-3]    -> Ticket Created: {ticket_info['ticket_id']} (Expires: {ticket_info['expires_at']})")
    print(f"[TIER-3]    -> Officer Endpoint: {ticket_info['review_endpoint']}")

    # 4. Customer-facing message: ONLY share the public ticket_id (NEVER expose the officer's JWT!)
    customer_reply = (
        "Your dispute requires review by our Risk & Compliance team and cannot be auto-processed. "
        f"We have logged your case under Ticket ID **{ticket_info['ticket_id']}**. "
        "A Compliance Officer will review your pre-filled audit dossier and respond within 24 hours."
    )

    return {
        "curr_tier": "tier_3_human",
        "needs_escalation": True,
        "escalation_reason": reason,
        "handoff_summary": handoff_summary,
        "escalation_ticket": ticket_info,
        "messages": [AIMessage(content=customer_reply)],
    }